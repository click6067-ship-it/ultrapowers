#!/usr/bin/env python3
"""spec_doctor — spec-decompose 시스템의 결정론적 검증/트리재생성 도구 (MVP).

절차 정본: 이 스킬의 SKILL.md (자기완결적). 설계 근거는 작성자 노트($COMMAND_CENTER/projects/, 선택).
stdlib만 사용(이식성). Python 3.8+.
역할(기계적인 일만 — prose 생성·완성판단 절대 안 함):
  1. master/child frontmatter 검증 (필수필드·중복 spec_id·고아 parent·깨진 source.path)
  2. master 섹션 해시 vs child source_hash 비교 → STALE 탐지
  3. ready leaf의 handoff_to_writing_plans 블록 완전성 검사
  4. tree.yaml 재생성 (--rebuild-tree) — derived 캐시 (정본은 파일+frontmatter)
  5. 드리프트 리포트 (silent recovery 금지 — 깨진 건 조용히 고치지 않고 *리포트*)

사용:
  spec_doctor.py <project_specs_dir>                 # 검증 + 드리프트 리포트
  spec_doctor.py <project_specs_dir> --rebuild-tree  # + tree.yaml 재생성
  spec_doctor.py <project_specs_dir> --json          # 기계판독 출력

종료코드: 0 = clean, 1 = 경고(stale/미완성), 2 = 에러(필수필드 누락·중복·고아).
"""
import sys, os, re, json, hashlib, argparse

# ---- frontmatter 파서 (PyYAML 의존 회피: 단순 YAML만 지원) ----
def parse_frontmatter(text):
    """--- ... --- 블록을 dict로. 중첩 1단계(2-space)까지 지원. 값은 str/list/dict."""
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return None, text
    body = text[m.end():]
    raw = m.group(1)
    fm = {}
    stack = [(-1, fm)]
    for line in raw.split('\n'):
        if not line.strip() or line.strip().startswith('#'):
            continue
        indent = len(line) - len(line.lstrip())
        key, _, val = line.strip().partition(':')
        key, val = key.strip(), val.strip()
        # strip inline comment (but not inside [...] list or quoted string)
        if val and not val.startswith('[') and not val.startswith('"') and not val.startswith("'"):
            val = val.split('#', 1)[0].strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if val == '':                      # nested map opens
            d = {}
            parent[key] = d
            stack.append((indent, d))
        elif val.startswith('[') and val.endswith(']'):
            inner = val[1:-1].strip()
            parent[key] = [x.strip().strip('"\'') for x in inner.split(',') if x.strip()] if inner else []
        else:
            parent[key] = val.strip('"\'')
    return fm, body

def section_hashes(master_text):
    """master 본문의 ## 헤더별 내용 해시. anchor(슬러그)→sha256[:12]."""
    _, body = parse_frontmatter(master_text)
    body = body if body else master_text
    hashes, cur, buf = {}, None, []
    for line in body.split('\n'):
        h = re.match(r'^##\s+(.+?)\s*$', line)
        if h:
            if cur is not None:
                hashes[cur] = _sha('\n'.join(buf))
            cur = slugify(h.group(1))
            buf = []
        else:
            buf.append(line)
    if cur is not None:
        hashes[cur] = _sha('\n'.join(buf))
    return hashes

def slugify(s):
    s = re.sub(r'^\d+[\.\)]\s*', '', s.strip())          # "1. Data" -> "Data"
    s = re.sub(r'[^\w가-힣\s-]', '', s).strip().lower()
    return re.sub(r'\s+', '-', s)

def _sha(s):
    return 'sha256:' + hashlib.sha256(s.encode('utf-8')).hexdigest()[:12]

REQUIRED_MASTER = ['spec_id', 'type', 'status']
REQUIRED_CHILD  = ['spec_id', 'type', 'parent']
HANDOFF_FIELDS  = ['scope', 'acceptance_criteria']   # readiness=ready leaf 최소 요건

def scan(specs_dir):
    nodes, errors, warnings = {}, [], []
    master = None
    md_files = []
    for root, _, files in os.walk(specs_dir):
        for f in files:
            if f.endswith('.md') and not f.endswith('tree.yaml'):
                md_files.append(os.path.join(root, f))
    for path in sorted(md_files):
        text = open(path, encoding='utf-8').read()
        fm, _ = parse_frontmatter(text)
        if not fm or 'spec_id' not in fm:
            continue                                       # spec 파일 아님(README 등) → 무시
        rel = os.path.relpath(path, specs_dir)
        sid = fm['spec_id']
        if sid in nodes:
            errors.append(f"중복 spec_id '{sid}': {rel} ↔ {nodes[sid]['path']}")
            continue
        nodes[sid] = {'fm': fm, 'path': rel, 'abspath': path, 'text': text}
        typ = fm.get('type', '')
        req = REQUIRED_MASTER if typ == 'master' else REQUIRED_CHILD
        for k in req:
            if k not in fm:
                errors.append(f"[{sid}] 필수필드 누락: '{k}' ({rel})")
        if typ == 'master':
            if master:
                errors.append(f"master 둘 이상: '{master}' ↔ '{sid}'")
            master = sid

    # 고아 parent + source.path 검증 + STALE + ready leaf
    mhashes = section_hashes(nodes[master]['text']) if master and master in nodes else {}
    children_of = {}
    for sid, n in nodes.items():
        fm = n['fm']
        if fm.get('type') == 'master':
            continue
        parent = fm.get('parent')
        if parent and parent not in nodes:
            errors.append(f"[{sid}] 고아 parent: '{parent}' 노드 없음 ({n['path']})")
        else:
            children_of.setdefault(parent, []).append(sid)
        # source.path 깨짐 검사
        src = fm.get('source', {}) if isinstance(fm.get('source'), dict) else {}
        spath = src.get('path')
        if spath:
            cand = os.path.join(specs_dir, spath)
            if not os.path.exists(cand):
                errors.append(f"[{sid}] 깨진 source.path: '{spath}' 파일 없음")
        # STALE: master 섹션 해시 vs child source_hash
        anchor = src.get('anchor')
        shash = src.get('source_hash')
        if anchor and shash and mhashes:
            cur = mhashes.get(anchor)
            if cur is None:
                warnings.append(f"[{sid}] source.anchor '{anchor}'가 master에 없음 (섹션 삭제/리네임?)")
            elif cur != shash:
                warnings.append(f"[{sid}] STALE: master '{anchor}' 변경됨 (기록 {shash} ≠ 현재 {cur}) → /reconcile-spec 필요")

    # ready leaf의 handoff 블록 완전성
    leaves = {sid for sid in nodes if nodes[sid]['fm'].get('type') != 'master' and sid not in children_of}
    for sid in leaves:
        fm = nodes[sid]['fm']
        readiness = None
        ho = fm.get('handoff_to_writing_plans')
        if isinstance(ho, dict):
            readiness = ho.get('readiness')
        status = fm.get('status', '')
        if status == 'approved' and readiness not in ('ready', 'out_of_scope'):
            errors.append(f"[{sid}] approved leaf인데 readiness={readiness!r} (ready|out_of_scope 아님) — handoff 게이트 위반")
        if isinstance(ho, dict) and readiness == 'ready':
            for fld in HANDOFF_FIELDS:
                v = ho.get(fld)
                if not v or (isinstance(v, list) and not v):
                    warnings.append(f"[{sid}] ready leaf인데 handoff.{fld} 비어있음 (자기선언 ready 검증 실패)")

    return {'master': master, 'nodes': nodes, 'children_of': children_of,
            'leaves': leaves, 'errors': errors, 'warnings': warnings, 'mhashes': mhashes}

def build_tree_yaml(result, specs_dir):
    """derived 캐시. 정본 아님. 수동편집 금지 헤더 포함."""
    lines = ['# AUTO-GENERATED by spec_doctor.py --rebuild-tree. 수동편집 금지 (정본=파일+frontmatter).',
             '# spec_doctor.py <dir> --rebuild-tree 로 재생성.', '']
    m = result['master']
    lines.append(f'root: {m or "(none)"}')
    lines.append('nodes:')
    for sid in sorted(result['nodes']):
        n = result['nodes'][sid]; fm = n['fm']
        lines.append(f'  {sid}:')
        lines.append(f'    path: {n["path"]}')
        lines.append(f'    type: {fm.get("type","")}')
        lines.append(f'    status: {fm.get("status","")}')
        if fm.get('parent'):
            lines.append(f'    parent: {fm["parent"]}')
        kids = result['children_of'].get(sid)
        if kids:
            lines.append('    children:')
            for k in sorted(kids):
                lines.append(f'      - {k}')
    return '\n'.join(lines) + '\n'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('specs_dir')
    ap.add_argument('--rebuild-tree', action='store_true')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    if not os.path.isdir(args.specs_dir):
        print(f"❌ 디렉토리 없음: {args.specs_dir}", file=sys.stderr); sys.exit(2)

    r = scan(args.specs_dir)
    if args.json:
        print(json.dumps({'master': r['master'], 'node_count': len(r['nodes']),
                          'leaf_count': len(r['leaves']), 'errors': r['errors'],
                          'warnings': r['warnings']}, ensure_ascii=False, indent=1))
    else:
        print(f"=== spec_doctor: {args.specs_dir} ===")
        print(f"master: {r['master']}  ·  nodes: {len(r['nodes'])}  ·  leaves: {len(r['leaves'])}")
        if r['errors']:
            print(f"\n🔴 ERRORS ({len(r['errors'])}):")
            for e in r['errors']: print(f"  - {e}")
        if r['warnings']:
            print(f"\n🟡 WARNINGS ({len(r['warnings'])}):")
            for w in r['warnings']: print(f"  - {w}")
        if not r['errors'] and not r['warnings']:
            print("\n✅ clean — 드리프트·누락·STALE 없음")

    if args.rebuild_tree and r['master']:
        out = os.path.join(args.specs_dir, 'tree.yaml')
        open(out, 'w', encoding='utf-8').write(build_tree_yaml(r, args.specs_dir))
        if not args.json:
            print(f"\n📄 tree.yaml 재생성: {out}")

    sys.exit(2 if r['errors'] else (1 if r['warnings'] else 0))

if __name__ == '__main__':
    main()
