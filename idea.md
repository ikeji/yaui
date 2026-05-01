# シェルスクリプトから使えるUIツールキット

- シェルスクリプトを含むほとんどのプログラミング言語で使える。
- Windows/GTK/TUI/Webで使える。

## 起動

次のようなShellScriptを書く。

```test.sh
#!/bin/sh

cat <<EOL
<
{"type":"dialog",
 "content": {"type":"label", "text":"Hello World!!"}
}
EOL

read f
```

これを、
yaui-gtk test.sh
という風に起動するとダイアログが表示される。

yaui-tui test.sh だとTUIで出る。
yaui-web test.sh だと、ブラウザが起動して表示される。

## 挙動

- スクリプトが出力した、JSON-treeを元にUIを出す。
- ボタンを押すなどすると、スクリプトの標準入力にJSONでイベントが伝えられる。
- スクリプトはイベントの応答、もしくは任意のタイミングで新しいUI JSONを出して画面を更新する。
  - 表示はReactJSみたいに差分更新する。

## UIコンポーネント

- dialog
- SDI
- hbox
- wbox
- tableview
- label
- button
- tab
- checkbox
- list
- textbox
- textarea
- logview
- progressbar
- icon
