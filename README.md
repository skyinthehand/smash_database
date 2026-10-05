# smash_database

> [!TIP]
> **データの誤りを見つけた方・データを確認してくださる方へ(コード不要)**
> 大会データのフォルダ構成と各ファイルの読み方を [**データを確認する方へ**](CONTRIBUTING.md#データを確認する方へ) にまとめています。
> 誤りは [**データの誤り報告フォーム**](https://github.com/skyinthehand/smash_database/issues/new?template=data_error.yml) から送れます。

[start.gg](https://www.start.gg/) から取得した大乱闘スマッシュブラザーズ SPECIAL の大会データ(順位・シード・対戦結果・選手情報)を集めたリポジトリです。
データは [`data/startgg/`](data/startgg/) にあります。

## ドキュメント

このリポジトリの設計・仕様・運用メモは `docs/` に集約しています。
以下のリンクから一覧できます。

- start.gg API 設計: [docs/startgg_design.md](docs/startgg_design.md)
- Data Model: [docs/data_model.md](docs/data_model.md)
- Directory 構成: [docs/directory.md](docs/directory.md)
- Flow: [docs/flow.md](docs/flow.md)
- GitHub Actions: [docs/github_actions.md](docs/github_actions.md)
- Fix / 不完全な点メモ: [docs/fix.md](docs/fix.md)

## 参加する

- [コントリビューションガイド](CONTRIBUTING.md)
- [行動規範](CODE_OF_CONDUCT.md)
- [セキュリティポリシー](SECURITY.md)

## ライセンス

コードは [MIT License](LICENSE) で公開しています。
`data/` 以下の大会データは start.gg から取得したもので、[start.gg の利用規約](https://www.start.gg/about/tos) に従います。
