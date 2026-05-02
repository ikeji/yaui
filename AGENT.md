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

4 つのランタイムは共通プロトコルを実装する独立した実行ファイル。プロトコル仕様は [`PROTOCOL.md`](PROTOCOL.md) を参照。

- `yaui-tui` … curses (Linux/macOS のターミナル)
- `yaui-gtk` … GTK 3 (Linux 主)
- `yaui-tk`  … Tkinter (クロスプラットフォーム、特に Windows / macOS で標準同梱なので推奨)
- `yaui-web` … HTTP + SSE で localhost ブラウザに描画

## ファイル配置

| ファイル        | 役割                                                  |
|-----------------|-------------------------------------------------------|
| `yaui-tui`      | curses ランタイム、Python 単一ファイル                |
| `yaui-gtk`      | GTK 3 ランタイム、PyGObject                           |
| `yaui-tk`       | Tkinter ランタイム、Python 単一ファイル               |
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

4 ランタイムとも、新しい UI ツリーを受信するたびに「id ベースの reconciliation」で既存ノードを再利用する。

- **TUI**: ウィジェットインスタンスは毎回作り直すが、状態（`text`, `cursor`, `checked`, `index`, `lines`）は `StateStore` が `id` をキーに保持する。UI ツリーで `value` を渡しても、`controlled: true` でない限り無視される。
- **GTK**: `App._idmap` が `id → (widget, type)` をフレームをまたいで保持。`apply_ui` の冒頭でキャッシュ済みウィジェットを全 `unparent`、新しい木の中で再 attach。Entry の `set_text` は signal を block して呼び出し、`get_position()` で位置を保存→`set_position(min(pos, len(new)))` で復元する。フレーム終了時に未参照になった id は `destroy()`。`get_focus()` で旧 focus 位置を id 単位で記録し、再描画後に `grab_focus()` で復元。
- **Tk**: tkinter は widget の reparenting を許さないので、毎フレーム木全体を作り直す。代わりに、apply 直前に `_capture_state()` で id 単位に `(value, cursor, focused, selected)` をスナップショット → 新しい木をビルドする `_build` 内で id にヒットするキャプチャを参照し、`_restore_input_value` で「focus 中かつ JSON 値と相違 → 旧値優先」「それ以外 → JSON 優先」のルールに従って初期値を決定。Listbox の選択も同様のルールで復元。
- **Web**: `ensure(existing, node)` が `(_yauiType, _yauiId)` で再利用判定。`reconcileChildren` は親 DOM 内のスロットを順番に更新／追加／削除（React の position-based reconciliation 風）。

textbox/textarea の `value` 上書きには共通ルール:
1. 新値 == 現在値 → 何もしない（カーソル維持）
2. 新値 ≠ 現在値かつ focus 中 → 何もしない（typeahead で打鍵中に script の echo back が既入力を消す race の回避）
3. focus が無ければ上書き
4. `node.controlled === true` なら 2 を無視して常に上書き

`launcher.sh` がこの不変条件を要求する典型例（dmenu_path 風: 入力でフィルタ、Enter で実行）。

### stderr の扱い

| ランタイム  | stderr の方針                                                 |
|-------------|---------------------------------------------------------------|
| yaui-tui    | キャプチャ（curses が同じターミナルを使うため出すと表示が崩れる） |
| yaui-gtk    | 親プロセスから継承（リアルタイム貫通）                         |
| yaui-tk     | 親プロセスから継承（リアルタイム貫通）                         |
| yaui-web    | 親プロセスから継承（リアルタイム貫通）                         |

### `--debug` の意味

| ランタイム  | 効果                                                              |
|-------------|-------------------------------------------------------------------|
| yaui-tui    | 未実装（curses 画面と stdout が衝突する）                         |
| yaui-gtk    | 受信した UI ツリーを `[yaui-gtk UI] ...` の形で stderr に出力     |
| yaui-tk     | 受信した UI ツリーを `[yaui-tk UI] ...` の形で stderr に出力      |
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

- `Hub` が「最新 UI ツリー (`_latest`)」と「id ごとの shadow (`_shadow`)」を保持
- マルチヘッド：複数タブ・別ブラウザが同時購読でき、片方の入力が他方に即座に反映される
- 新規購読者には接続時に `('ui', latest)` を送り、続けて shadow の各エントリを `('peer', entry)` で順次 replay → リロードや遅参 tab が自動的に追従
- `relay_peer(event)` が `_handle_event` から呼ばれ、shadow を更新しつつ全 SSE 購読者へ `event: peer` を broadcast。クライアントは `applyPeer` で `[data-yaui-id="..."]` を引き、focus 中なら無視・そうでなければ DOM の値を更新
- `_refresh_shadow_from_tree` が UI ツリー emit 時に `value`/`checked`/`selected` を shadow にミラー → スクリプト主導のリセットで shadow が腐らない
- 終了時は `Hub.shutdown()` で全クライアントに `event: end` を送ってからプロセス終了
- 内蔵 HTML/JS は単一の `INDEX_HTML` 文字列。別ファイルに分けない方針（単一バイナリ感を保つため）
- ブラウザのタブ閉じでは close を自動送信しない（マルチヘッド前提でスクリプトはタブをまたいで生きる）。明示的な終了が必要なら UI に Quit ボタンを置くか、yaui-web プロセスを Ctrl+C
- `keepalive: true` を `fetch('/event')` に付けてナビゲーション中でも POST 取りこぼし防止

## テスト戦略

| ファイル        | カバー範囲                                                      |
|-----------------|-----------------------------------------------------------------|
| `test_e2e.py`   | yaui-tui を pty で起動し、Enter / Esc で 2 段階の UI 切替を確認 |
| `test_gtk.py`   | Xvfb 上で yaui-gtk を起動、ウィンドウが現れて N tick 描画→exit 0 |
| `test_tk.py`    | Xvfb 上で yaui-tk  を起動、同上                                  |
| `test_web.py`   | yaui-web を `--no-browser` で起動、curl + urllib で 3 endpoint 検証 |
| `test_web_multihead.py` | 2 つの SSE クライアントで peer broadcast / shadow replay を検証 |

合成入力ツール（xdotool / python-xlib / pyatspi）は環境にないので、GTK と Web のテストはユーザー操作の代わりに「スクリプト主導で UI を更新して自然終了する fixture」を使う。視覚確認には ImageMagick の `import` でスクリーンショット取得。

## 新しいウィジェットの追加チェックリスト

1. `yaui-tui` の `build()` と新しい `Widget` クラスを追加
2. `yaui-gtk` の `_create_widget` / `_update_widget` に分岐を追加
3. `yaui-tk` の `_build` に分岐を追加（必要なら `_capture_state` も拡張）
4. `yaui-web` の `INDEX_HTML` 内 `create` / `update` (JS) に分岐を追加
5. `PROTOCOL.md` のウィジェット一覧に追加
6. テストは可能なら `showcase.sh` に並べる
7. すべてのランタイムでフォールバック（`<unknown widget>`）に落ちないか確認

## やりがちな落とし穴

- **追加し忘れ**: 1 ランタイムだけに足すと他で `<unknown widget>` が表示される。コミット前に必ず 4 つすべてに反映する
- **GTK のスレッド境界**: reader スレッドから直接 GTK API を呼ぶと segfault。必ず `GLib.idle_add`
- **Web の DOM 全再構築**: textbox/textarea の `change` で再描画するとカーソル飛び。デモはこの罠を回避する書き方をしている
- **再エミット時の `value` 扱い**: TUI は無視、GTK/Web は適用、という非対称をユーザースクリプトに見せないため、`controlled` フラグを使うか、`change` を素直に echo back する。
- **JSON エンコード/デコード**: シェルから JSON を扱うときは正規表現で頑張らず `python3 -c '...'` を呼ぶ方が壊れない（`showcase.sh` の `extract` / `json_body` 参照）

## 規約

- ランタイムは依存最小。yaui-tui / yaui-web は標準ライブラリのみ。yaui-gtk は GTK のため PyGObject。
- 既存ファイルへの編集を優先。新規ファイルは必要最小限。
- スクリプトは bash でも sh でも書けるよう、極力 POSIX 寄りに。bash 固有機能（`read -t`、`[[ =~ ]]`、`<<<`）は使ってよいが、その場合 `#!/bin/bash` を明示。
- ランタイムはスクリプトの環境に `YAUI=tui|gtk|web` を設定する。
