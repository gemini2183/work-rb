#!/usr/bin/env python3
"""claude_usage.py — расход токенов Claude Code по сессиям и агентам. ТОЛЬКО ЧТЕНИЕ.

Источник: журналы ~/.claude/projects/<проект>/<сессия>.jsonl (основная сессия) и
<сессия>/subagents/agent-<id>.jsonl (+ .meta.json с описанием агента). Ничего не пишет,
в API не ходит. Каждый вызов модели записан несколькими строками (по блоку контента),
поэтому считаем один раз на message.id.

Единицы «вес»: токены ввода по цене обычного ввода = 1.0; запись кэша 5 мин = 1.25;
запись кэша 1 ч = 2.0; чтение кэша = 0.1; вывод = 5.0 (множители кэша — из документации
Anthropic; множитель вывода 5× — допущение для линейки Sonnet, для 5.5 НЕ проверено).
Это сравнительная мера, а не доллары и не процент лимита подписки.

Режимы:
  python Скрипты/claude_usage.py                       # сессии проекта за 7 дней
  python Скрипты/claude_usage.py --since 2026-11-10 --top 15
  python Скрипты/claude_usage.py --agents --session 33277b70      # агенты сессии
  python Скрипты/claude_usage.py --returns --session 33277b70     # стоимость каждого возврата (SendMessage)
  python Скрипты/claude_usage.py --turns --session 66fa4180       # реплики основной сессии
  python Скрипты/claude_usage.py --all-projects                   # все папки ~/.claude/projects
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECTS = Path.home() / ".claude" / "projects"
DEFAULT_PROJECT = "d--GitHub-work-rb"
W_IN, W_CW5, W_CW1H, W_CR, W_OUT = 1.0, 1.25, 2.0, 0.1, 5.0
CACHE_TTL_S = 300  # 5 минут


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class Call:
    __slots__ = ("ts", "inp", "cw5", "cw1", "cr", "out", "model", "prompt_id")

    def __init__(self, ts, u, model, prompt_id):
        self.ts = ts
        self.inp = u.get("input_tokens", 0) or 0
        cc = u.get("cache_creation") or {}
        cw_total = u.get("cache_creation_input_tokens", 0) or 0
        self.cw1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
        self.cw5 = cc.get("ephemeral_5m_input_tokens", cw_total - self.cw1) or 0
        self.cr = u.get("cache_read_input_tokens", 0) or 0
        self.out = u.get("output_tokens", 0) or 0
        self.model = model
        self.prompt_id = prompt_id

    @property
    def weight(self):
        return (self.inp * W_IN + self.cw5 * W_CW5 + self.cw1 * W_CW1H
                + self.cr * W_CR + self.out * W_OUT)

    @property
    def cw(self):
        return self.cw5 + self.cw1

    @property
    def ctx(self):  # размер контекста, который модель увидела в этом вызове
        return self.inp + self.cw + self.cr


def read_calls(path: Path):
    """Возвращает (calls, user_starts): вызовы модели без дублей и начала реплик
    (user-строки с текстом, не tool_result) с promptId."""
    calls, seen, starts = [], set(), []
    cur_prompt = None
    try:
        fh = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return calls, starts
    with fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = r.get("type")
            if t == "user":
                m = r.get("message") or {}
                c = m.get("content")
                is_text = isinstance(c, str) or (
                    isinstance(c, list) and not any(b.get("type") == "tool_result" for b in c if isinstance(b, dict)))
                pid = r.get("promptId")
                if is_text and pid and pid != cur_prompt and not r.get("isMeta"):
                    cur_prompt = pid
                    txt = c if isinstance(c, str) else " ".join(
                        b.get("text", "") for b in c if isinstance(b, dict))
                    starts.append((r.get("timestamp"), pid, txt))
            elif t == "assistant":
                m = r.get("message") or {}
                u = m.get("usage")
                if not u:
                    continue
                key = m.get("id") or r.get("requestId") or r.get("uuid")
                if key in seen:
                    continue
                seen.add(key)
                calls.append(Call(parse_ts(r["timestamp"]), u, m.get("model", "?"), cur_prompt))
    calls.sort(key=lambda c: c.ts)
    return calls, starts


def totals(calls):
    d = dict(n=len(calls), inp=0, cw=0, cr=0, out=0, w=0.0)
    for c in calls:
        d["inp"] += c.inp
        d["cw"] += c.cw
        d["cr"] += c.cr
        d["out"] += c.out
        d["w"] += c.weight
    return d


def fmt(n):
    return f"{n:,}".replace(",", " ")


def short_model(calls):
    ms = {c.model for c in calls if c.model and c.model != "<synthetic>"}
    return ",".join(sorted(m.replace("claude-", "") for m in ms)) or "?"


def agent_meta(path: Path):
    meta = path.with_suffix(".meta.json")
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def session_files(proj: Path):
    for f in proj.glob("*.jsonl"):
        yield f.stem, f, sorted((proj / f.stem / "subagents").glob("agent-*.jsonl"))


def header(cols):
    print(" | ".join(cols))
    print("-|-".join("-" * len(c) for c in cols))


def cmd_sessions(args, projs):
    since = args.since
    rows = []
    for proj in projs:
        for sid, main, subs in session_files(proj):
            mc, _ = read_calls(main)
            sc = []
            for s in subs:
                sc.extend(read_calls(s)[0])
            allc = mc + sc
            if not allc or allc[-1].ts < since:
                continue
            if args.session and not sid.startswith(args.session):
                continue
            tm, ts_ = totals(mc), totals(sc)
            rows.append((tm["w"] + ts_["w"], proj.name, sid, allc[0].ts, allc[-1].ts, tm, ts_, short_model(allc), len(subs)))
    rows.sort(reverse=True)
    print(f"# Сессии с {since:%Y-%m-%d} (вес = взвешенные токены, тыс.; допущения — в шапке скрипта)\n")
    header(["сессия", "начало (UTC)", "длит.", "вызовов", "вес осн., тыс", "вес агентов, тыс", "агентов", "чтение кэша, млн", "запись кэша, тыс", "вывод, тыс", "модель"])
    tot_w = 0
    for w, pn, sid, t0, t1, tm, ts_, mod, nsub in rows[: args.top]:
        dur = t1 - t0
        h = dur.total_seconds() / 3600
        print(f"{sid[:8]} | {t0:%m-%d %H:%M} | {h:.1f}ч | {tm['n'] + ts_['n']} | {tm['w']/1000:,.0f} | {ts_['w']/1000:,.0f} | {nsub} | "
              f"{(tm['cr'] + ts_['cr'])/1e6:.1f} | {(tm['cw'] + ts_['cw'])/1000:,.0f} | {(tm['out'] + ts_['out'])/1000:,.0f} | {mod}".replace(",", " "))
    for r in rows:
        tot_w += r[0]
    print(f"\nИтого по {len(rows)} сессиям: {tot_w/1e6:.1f} млн взвешенных токенов; показано {min(len(rows), args.top)}.")


def cmd_agents(args, projs):
    print(f"# Агенты с {args.since:%Y-%m-%d}\n")
    header(["сессия", "агент", "тип", "описание", "модель", "вызовов", "старт: ctx первого вызова", "последний ctx", "вес, тыс", "вывод, тыс"])
    for proj in projs:
        for sid, main, subs in session_files(proj):
            if args.session and not sid.startswith(args.session):
                continue
            for s in subs:
                calls, _ = read_calls(s)
                if not calls or calls[-1].ts < args.since:
                    continue
                m = agent_meta(s)
                t = totals(calls)
                print(f"{sid[:8]} | {s.stem[6:14]} | {m.get('agentType', '?')} | {m.get('description', '')[:45]} | {short_model(calls)} | "
                      f"{t['n']} | {fmt(calls[0].ctx)} | {fmt(calls[-1].ctx)} | {t['w']/1000:,.0f} | {t['out']/1000:,.0f}".replace(",", " "))


def cmd_returns(args, projs):
    """Стоимость каждого возврата агента (SendMessage): реплики-продолжения внутри файла агента."""
    print("# Возвраты агентов: реплика = первое задание или сообщение координатора (SendMessage)\n")
    print("Колонки: пауза = простой перед репликой; 1-й вызов — что модель сделала с кэшем (запись = кэш протух, прочитан = жив).\n")
    header(["сессия", "агент", "реплика", "время UTC", "пауза", "вызовов", "ctx на входе", "1-й вызов: запись кэша", "1-й вызов: чтение кэша", "вес реплики, тыс", "вывод, тыс"])
    for proj in projs:
        for sid, main, subs in session_files(proj):
            if args.session and not sid.startswith(args.session):
                continue
            for s in subs:
                calls, starts = read_calls(s)
                if not calls:
                    continue
                m = agent_meta(s)
                label = f"{s.stem[6:14]} {m.get('description', '')[:28]}"
                by = defaultdict(list)
                for c in calls:
                    by[c.prompt_id].append(c)
                order = [p for _, p, _ in starts if p in by]
                prev_end = None
                for i, p in enumerate(order):
                    cs = by[p]
                    gap = (cs[0].ts - prev_end).total_seconds() if prev_end else 0
                    t = totals(cs)
                    first = cs[0]
                    print(f"{sid[:8]} | {label} | #{i} | {cs[0].ts:%H:%M:%S} | {gap/60:.1f} мин | {t['n']} | {fmt(first.ctx)} | "
                          f"{fmt(first.cw)} | {fmt(first.cr)} | {t['w']/1000:,.0f} | {t['out']/1000:,.1f}".replace(",", " "))
                    prev_end = cs[-1].ts


def cmd_turns(args, projs):
    print("# Реплики основной сессии\n")
    header(["сессия", "реплика", "время UTC", "вызовов", "ctx в конце", "вес, тыс", "вывод, тыс", "начало текста"])
    for proj in projs:
        for sid, main, subs in session_files(proj):
            if not args.session or not sid.startswith(args.session):
                continue
            calls, starts = read_calls(main)
            by = defaultdict(list)
            for c in calls:
                by[c.prompt_id].append(c)
            for i, (ts, p, txt) in enumerate(starts):
                cs = by.get(p, [])
                if not cs:
                    continue
                t = totals(cs)
                print(f"{sid[:8]} | #{i} | {cs[0].ts:%m-%d %H:%M} | {t['n']} | {fmt(cs[-1].ctx)} | {t['w']/1000:,.0f} | {t['out']/1000:,.1f} | {txt[:50]!r}".replace(",", " "))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=DEFAULT_PROJECT, help="имя папки в ~/.claude/projects")
    ap.add_argument("--all-projects", action="store_true")
    ap.add_argument("--since", default=None, help="ГГГГ-ММ-ДД (по умолчанию 7 дней назад)")
    ap.add_argument("--session", help="префикс id сессии")
    ap.add_argument("--top", type=int, default=20)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--agents", action="store_true")
    g.add_argument("--returns", action="store_true")
    g.add_argument("--turns", action="store_true")
    args = ap.parse_args()
    args.since = (datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since
                  else datetime.now(timezone.utc) - timedelta(days=7))
    if args.all_projects:
        projs = [p for p in PROJECTS.iterdir() if p.is_dir()]
    else:
        projs = [PROJECTS / args.project]
    if args.agents:
        cmd_agents(args, projs)
    elif args.returns:
        cmd_returns(args, projs)
    elif args.turns:
        cmd_turns(args, projs)
    else:
        cmd_sessions(args, projs)


if __name__ == "__main__":
    main()
