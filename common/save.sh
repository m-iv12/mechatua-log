#!/bin/bash
# 取得結果をリポジトリに保存する（8人共通）。
# 同じ時間にほかの実行（ポストの追加が続いたときなど）が posts.json などを先に書き換えていて衝突した場合は、
# 自分の変更を捨てて最新の状態に戻し、追加と取得をやり直してから保存する（最大5回）。
set -u
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

for i in 1 2 3 4 5; do
  git add -A -- *.json
  if git diff --cached --quiet; then
    echo "変更なし"
    exit 0
  fi
  git commit -q -m "配信データを更新"
  # 共通のプログラムで上書きした .py は保存しない（変更が残っていると pull できないため元に戻す）
  git checkout -- fetch_streams.py add_item.py 2>/dev/null || true
  if git pull -q --rebase origin main && git push -q origin HEAD:main; then
    echo "保存しました"
    exit 0
  fi
  echo "ほかの更新と重なったため、最新の状態からやり直します（${i} 回目）"
  git rebase --abort 2>/dev/null || true
  git fetch -q origin main
  git reset -q --hard origin/main
  cp /tmp/shared/fetch_streams.py /tmp/shared/add_item.py . 2>/dev/null || true
  sleep $((RANDOM % 20 + 5))
  if [ "${IS_ISSUE:-0}" = "1" ]; then python add_item.py || exit 1; fi
  FULL_REFRESH=0 python fetch_streams.py || exit 1
done
echo "5回やり直しても保存できませんでした"
exit 1
