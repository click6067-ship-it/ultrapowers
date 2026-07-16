#!/bin/bash
# doc2txt.sh <파일.hwp|.hwpx|.pdf> [출력.txt] — 한글/PDF 문서를 텍스트로 추출.
# 🤖 왜: Claude Read는 hwp를 못 읽는다(12세션 실측 반복 씨름). 이 스크립트가 표준 경로.
#   .hwp  → hwp5txt(pyhwp, 설치됨)  ·  .hwpx → zip+XML 파싱  ·  .pdf → pdftotext(poppler-utils)
#   출력 생략 시 stdout. PDF는 Read 도구가 네이티브 지원하므로 pdftotext는 벌크/파이프용.
set -euo pipefail
f="$1"; out="${2:-/dev/stdout}"
[ -f "$f" ] || { echo "없음: $f" >&2; exit 1; }
case "${f,,}" in
  *.hwp)
    BIN="$HOME/.local/bin"
    HWP5TXT="$(command -v hwp5txt || echo "$BIN/hwp5txt")"
    [ -x "$HWP5TXT" ] || { echo "hwp5txt 없음 — pip install --user pyhwp" >&2; exit 2; }
    tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
    "$HWP5TXT" "$f" > "$tmp" || true
    # 표 위주 문서는 hwp5txt가 <표> 마커만 남김 → 수확량 적으면 hwp5proc xml 폴백(표 셀 텍스트 포함)
    # (grep [가-힣]은 C 로케일에서 collation 에러 — python으로 카운트)
    yield=$(python3 -c 'import re,sys;print(len(re.findall(r"[0-9A-Za-z가-힣]",open(sys.argv[1],encoding="utf-8",errors="replace").read())))' "$tmp")
    if [ "$yield" -lt 200 ]; then
      HWP5PROC="$(command -v hwp5proc || echo "$BIN/hwp5proc")"
      "$HWP5PROC" xml "$f" 2>/dev/null | python3 -c '
import html, re, sys
buf = []
for chunk in re.split(r"(</Paragraph>)", sys.stdin.read()):
    if chunk == "</Paragraph>":
        line = " ".join(buf).strip()
        if line: print(line)
        buf = []
    else:
        buf += [html.unescape(t) for t in re.findall(r"<Text[^>]*>([^<]+)</Text>", chunk)]
' > "$out"
    else
      cat "$tmp" > "$out"
    fi ;;
  *.hwpx)
    # hwpx = OWPML zip. Contents/section*.xml에서 태그 제거해 텍스트만.
    python3 - "$f" > "$out" <<'PY'
import re, sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
secs = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n))
for n in secs:
    xml = z.read(n).decode("utf-8", "replace")
    # 문단 경계 보존: </hp:p> → 개행, 나머지 태그 제거
    txt = re.sub(r"</hp:p>", "\n", xml)
    txt = re.sub(r"<[^>]+>", "", txt)
    print(re.sub(r"\n{3,}", "\n\n", txt).strip())
PY
    ;;
  *.pdf)
    command -v pdftotext >/dev/null || { echo "pdftotext 없음 — sudo apt-get install -y poppler-utils (또는 Claude Read 도구로 직접)" >&2; exit 2; }
    pdftotext -layout "$f" "$out" ;;
  *) echo "지원 안 함: $f (hwp/hwpx/pdf만)" >&2; exit 1 ;;
esac
