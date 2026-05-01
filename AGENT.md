# AGENT.md

このリポジトリで作業するエージェント・コントリビュータ向けの開発ノート。

## 全体像

```
            ┌────────┐
            │ script │ ← stdin:  events
            │  (sh)  │ → stdout: UI trees
            └───┬────┘
                │
       ┌────────┼────────┐
       ▼        ▼        ▼
   yaui-tui yaui-gtk yaui-web
   (curses) (GTK 3)  (HTTP/SSE)
```

3 つのランタイムは共通プロトコルを実装する独立した実行ファイル。プロトコル仕様は [`PROTOCOL.md`](PROTOCOL.md) を参照。

## ファイル配置

| ファイル        | 役割                                                  |
|-----------------|-------------------------------------------------------|
| `yaui-tui`      | curses ランタイム、Python 単一ファイル                |
| `yaui-gtk`      | GTK 3 ランタイム、PyGObject                           |
| `yaui-web`      | HTTP + SSE ランタイム + 内蔵 HTML/JS クライアント     |
| `idea.md`       | 元の設計メモ（不変）                                  |
| `PROTOCOL.md`   | プロトコル仕様（ユーザー向け）                        |
| `README.md`     | プロジェクトトップ                                    |
| `AGENT.md`      | 本ファイル                                            |
| `test_e2e.py`   | yaui-tui 用 E2E（pty 経由）                            |
| `test_gtk.py`   | yaui-gtk 用 E2E（Xvfb）                                |
| `test_web.py`   | yaui-web 用 E2E（curl + urllib）                       |
| `*.sh`          | デモ／テスト用スクリプト                              |

## 共通実装トピック

### JSON ストリームパーサ（3 ランタイムで重複コピー）

- 1 文字ずつ読みながら `{` `[` の深さを追う
- `"..."` 内の文字とエスケープ（`\"`、`\\`）を正しくスキップ
- 深さ 0 に戻った時点で `json.loads()`、失敗してもスキップして次へ
- 先頭が `{` `[` でないバイトは捨てる（同期外れからの自動復帰）

3 つの実装で同一コードがある。1 箇所で直したら他の 2 つも揃えること。

### スクリプト起動

`subprocess.Popen` で起動する際、相対パスのファイル名（例 `monitor.sh`）は PATH 検索に乗らないため発見できない。3 つの実装とも、cwd に存在する場合は `os.path.abspath()` で絶対パスに正規化する。実行ビットが立っていなければ `/bin/sh` 経由で起動する。

### 状態保持の方針の違い

- **TUI**: ウィジェットインスタンスは毎回作り直すが、状態（`text`, `cursor`, `checked`, `index`, `lines`）は `StateStore` が `id` をキーに保持する。UI ツリーで `value` を渡しても、`controlled: true` でない限り無視される。
- **GTK / Web**: 全再構築。ユーザー入力を保つには、スクリプト側で `change` イベントを捕捉してから次回の UI ツリーに `value` として echo back する。これは React の controlled input と同じ思想。

ただし全再描画は、textbox/textarea の打鍵ごとにやるとカーソルが先頭へ飛ぶ。デモは「打鍵時の `change` では変数だけ更新して再エミットしない」「ボタン押下や選択など、別のイベントで再エミット」というパターンを採用している（`showcase.sh` 参照）。

### stderr の扱い

| ランタイム  | stderr の方針                                                 |
|-------------|---------------------------------------------------------------|
| yaui-tui    | キャプチャ（curses が同じターミナルを使うため出すと表示が崩れる） |
| yaui-gtk    | 親プロセスから継承（リアルタイム貫通）                         |
| yaui-web    | 親プロセスから継承（リアルタイム貫通）                         |

### `--debug` の意味

| ランタイム  | 効果                                                              |
|-------------|-------------------------------------------------------------------|
| yaui-tui    | 未実装（curses 画面と stdout が衝突する）                         |
| yaui-gtk    | 受信した UI ツリーを `[yaui-gtk UI] ...` の形で stderr に出力     |
| yaui-web    | 上記 + HTTP リクエストログ                                        |

## ランタイム別の実装メモ

### yaui-tui

- `Widget` 基底クラス → 各ウィジェット
- レイアウトは vbox/hbox の `measure()` で必要サイズを返し、親が分配する単純方式
- 入力は `stdscr.timeout(50)` のポーリングで queue を draine
- Esc は `close` を送って `script.close_stdin()` し、スクリプトの終了を待つ
- フォーカスは `collect_focusables(out)` で再帰収集、Tab/Shift-Tab で循環

### yaui-gtk

- バックグラウンドの reader スレッドで stdout をパース → `script.q` に投入
- `App.consume()` がそれをポーリングして `GLib.idle_add(self.apply_ui, payload)` でメインスレッドへ橋渡し（GTK は必ずメインスレッドから呼ぶ）
- 毎回 `_replace_child` で window のコンテンツごと差し替えている
- `destroy` シグナルと Esc キーで `close` 発火

### yaui-web

- `Hub` クラスが「最新 UI ツリー」と「購読中の SSE クライアント」のキュー群を保持
- 新しい SSE 接続には最新ツリーを即座に送るので、ブラウザのリロードで状態が崩れない
- 終了時は `Hub.shutdown()` で全クライアントに `event: end` を送ってからプロセス終了
- 内蔵 HTML/JS は単一の `INDEX_HTML` 文字列。別ファイルに分けない方針（単一バイナリ感を保つため）
- ブラウザのタブを閉じると `beforeunload` で `navigator.sendBeacon('/event', {type:close})` を投げる（`fetch` の `keepalive` も使用）

## テスト戦略

| ファイル        | カバー範囲                                                      |
|-----------------|-----------------------------------------------------------------|
| `test_e2e.py`   | yaui-tui を pty で起動し、Enter / Esc で 2 段階の UI 切替を確認 |
| `test_gtk.py`   | Xvfb 上で yaui-gtk を起動、ウィンドウが現れて N tick 描画→exit 0 |
| `test_web.py`   | yaui-web を `--no-browser` で起動、curl + urllib で 3 endpoint 検証 |

合成入力ツール（xdotool / python-xlib / pyatspi）は環境にないので、GTK と Web のテストはユーザー操作の代わりに「スクリプト主導で UI を更新して自然終了する fixture」を使う。視覚確認には ImageMagick の `import` でスクリーンショット取得。

## 新しいウィジェットの追加チェックリスト

1. `yaui-tui` の `build()` と新しい `Widget` クラスを追加
2. `yaui-gtk` の `build_widget()` に分岐を追加
3. `yaui-web` の `INDEX_HTML` 内 `build()` 関数（JS）に分岐を追加
4. `PROTOCOL.md` のウィジェット一覧に追加
5. テストは可能なら `showcase.sh` に並べる
6. すべてのランタイムでフォールバック（`<unknown widget>`）に落ちないか確認

## やりがちな落とし穴

- **追加し忘れ**: 1 ランタイムだけに足すと他で `<unknown widget>` が表示される。コミット前に必ず 3 つすべてに反映する
- **GTK のスレッド境界**: reader スレッドから直接 GTK API を呼ぶと segfault。必ず `GLib.idle_add`
- **Web の DOM 全再構築**: textbox/textarea の `change` で再描画するとカーソル飛び。デモはこの罠を回避する書き方をしている
- **再エミット時の `value` 扱い**: TUI は無視、GTK/Web は適用、という非対称をユーザースクリプトに見せないため、`controlled` フラグを使うか、`change` を素直に echo back する。
- **JSON エンコード/デコード**: シェルから JSON を扱うときは正規表現で頑張らず `python3 -c '...'` を呼ぶ方が壊れない（`showcase.sh` の `extract` / `json_body` 参照）

## 規約

- ランタイムは依存最小。yaui-tui / yaui-web は標準ライブラリのみ。yaui-gtk は GTK のため PyGObject。
- 既存ファイルへの編集を優先。新規ファイルは必要最小限。
- スクリプトは bash でも sh でも書けるよう、極力 POSIX 寄りに。bash 固有機能（`read -t`、`[[ =~ ]]`、`<<<`）は使ってよいが、その場合 `#!/bin/bash` を明示。
- ランタイムはスクリプトの環境に `YAUI=tui|gtk|web` を設定する。
