# コントリビューションガイド

smash_database への協力に興味を持っていただきありがとうございます。

- **データの中身を確認して、誤りを報告してくださる方** → [データを確認する方へ](#データを確認する方へ)
- **スクリプトやワークフローを修正してくださる方** → [コードを変更する方へ](#コードを変更する方へ)

---

## データを確認する方へ

コードを書く必要はありません。GitHub をブラウザで見られれば、それだけでデータの確認と誤りの報告ができます。
見つけた誤りは [「データの誤り報告」Issue](https://github.com/skyinthehand/smash_database/issues/new?template=data_error.yml) から送ってください。

### 1. 大会のデータを探す

すべての大会データは [`data/startgg/events/`](data/startgg/events/) の下に、次の階層で保存されています。

```
data/startgg/events/
└── {地域}/
    └── {年}/{月}/{日}/
        └── {大会名}/
            └── {イベント名}/
                ├── attr.json       … イベントの基本情報(大会名・日時・参加者数・会場など)
                ├── standings.json  … 最終順位
                ├── seeds.json      … シード順
                └── matches.json    … 対戦結果(スコア・キャラクター・ステージ)
```

例: `data/startgg/events/Japan/2025/06/06/晴れスマ#48/晴れスマ#48/standings.json`

いちばん早い探し方は、リポジトリのトップページでキーボードの **`t`** を押し(または **Go to file** をクリックし)、大会名の一部を入力することです。

#### 地域

| フォルダ名 | 含まれる国 |
| --- | --- |
| `Japan` | 日本 |
| `Other_Asia` | 中国・韓国・インド・シンガポール・タイ・マレーシア・フィリピン・ベトナム・インドネシア |
| `Europe` | フランス・ドイツ・イギリス・イタリア・スペイン・ロシア・オランダ・スウェーデン・スイス・ベルギー |
| `North_America` | アメリカ・カナダ・ドミニカ共和国・メキシコ |
| `Other` | 上記以外の国、およびオンライン大会など国が設定されていない大会 |

#### 日付は「大会開始日時の UTC(協定世界時)」です

フォルダの日付は、start.gg に登録された**大会の開始日時を UTC で表した日付**です。日本時間ではありません。
そのため、**日本時間の 0:00〜8:59 に始まる大会は、前日の日付のフォルダに入ります**。

> 例: 日本時間 2025年6月7日 0:00 開始の「晴れスマ#48」は `Japan/2025/06/06/` にあります。

また、日付はイベントごとではなく**大会全体の開始日時**で決まります。複数日にわたる大会では、2日目以降のイベントも初日のフォルダに入ります。

#### 大会名・イベント名の書き換え

フォルダ名は start.gg 上の名前を元に、次のように書き換えています。

- 半角スペース → `_`(アンダースコア)
- `/`(スラッシュ) → `-`(ハイフン)

同じ日・同じ地域に同名の別大会があった場合、参加者の少ない方のフォルダ名は `大会名_(大会ID)` の形になります。

### 2. ファイルの中身を読む

すべてのファイルは JSON 形式です。GitHub 上で開くとそのまま読めます。
各項目の詳しい意味は [docs/data_model.md](docs/data_model.md) にあります。ここでは確認によく使う項目だけを説明します。

#### `attr.json`(イベントの基本情報)

| 項目 | 意味 |
| --- | --- |
| `tournament_name` / `event_name` | 大会名 / イベント名 |
| `url` | start.gg 上の大会ページ。`https://www.start.gg` の後ろにつなげると開けます(例: `/tournament/48-6` → `https://www.start.gg/tournament/48-6`) |
| `timestamp` / `end_at` | 大会の開始 / 終了日時(UNIX 時間。[変換サイト](https://www.epochconverter.com/)などで日時に直せます) |
| `num_entrants` | 参加者数 |
| `offline` | `true` ならオフライン大会 |
| `place` | 会場の国・都市・住所など |
| `labels` | 大会の種類の分類(下の「誤りではないもの」も参照) |

#### `standings.json` / `seeds.json`(順位 / シード)

```json
{"placement": 1, "user_id": 111, "player_id": 211}
```

選手は**名前ではなく ID** で記録されています。
ID から選手名を調べるには、[`data/startgg/users.jsonl`](data/startgg/users.jsonl) を開いて **Raw** ボタンを押し、ブラウザのページ内検索(Ctrl+F / ⌘+F)で `"user_id": 111,` を探してください。同じ行の `gamer_tag` が選手名です。
ファイルが大きい(約 20MB)ため、開くまで少し時間がかかります。

#### `matches.json`(対戦結果)

1件が1セット(1試合)です。`winner_id` / `loser_id` は上と同じ `user_id`、`winner_score` / `loser_score` はセットのスコアです。
`details` には各ゲームのステージと使用キャラクターが入っています(大会側で入力されていない場合は空です)。

### 3. start.gg と見比べる

`attr.json` の `url` から start.gg の大会ページを開き、順位・スコア・参加者数などを見比べてください。
特に次のような違いは、報告していただけるととても助かります。

- 順位・スコア・勝敗が start.gg と違う
- 参加者数が大きく違う、選手が抜けている
- 大会の日付や地域のフォルダが明らかに違う(上の「日付は UTC」の説明も確認してください)
- 同じ大会・イベントが2か所に保存されている
- `attr.json` があるのに、`matches.json` に `{"set_id": 123}` のように `set_id` しかない行が残っている
- start.gg 上で終了しているのに、大会がまったく保存されていない

### 4. 誤りではないもの(既知の仕様)

次のものはデータの性質上そうなっているもので、誤りではありません。

- **`user_id` が `null`**: ダブルスやチーム戦の参加者、start.gg アカウントに紐付いていないゲスト参加者は `null` になることがあります。
- **`labels` の `registration_type` / `event_type` / `game_rule` の値**: AI による推定で、正確さは保証していません。明らかにおかしいものは報告していただいて構いません。
- **古いイベントに項目が足りない**: データの形式は段階的に拡張されていて、古いイベントには新しい項目(`end_at`、`player_id` など)がまだないことがあります。`event_data_version` が小さいイベントは、自動の補完処理で順次更新されます。
- **開催中・未終了の大会がない**: 終了した大会だけを保存しています。
- **最新の大会がまだない**: 日本の大会は毎日 日本時間 3:00 頃に自動で取得しています。終了直後の大会は、翌日以降に反映されます。
- **意図的に除外しているイベント**: [`config/startgg/excluded_events.json`](config/startgg/excluded_events.json) に載っているイベントは、理由があって取得対象から外しています。

### 5. 報告する

[「データの誤り報告」Issue](https://github.com/skyinthehand/smash_database/issues/new?template=data_error.yml) のフォームから送ってください。フォームの各欄を埋めるだけで報告できます。
報告をいただくと、管理者がスクリプトでデータを再取得・修正します。データファイルを直接編集した Pull Request は、ほかのデータとの整合が崩れるため受け付けていません。

---

## コードを変更する方へ

### 準備

```bash
git clone https://github.com/skyinthehand/smash_database.git
cd smash_database
python -m pip install -r requirements.txt
```

start.gg からデータを取得するスクリプトを動かすには、start.gg の API トークンが必要です([start.gg の開発者向けページ](https://developer.start.gg/docs/authentication)で発行できます)。
トークンは `--token` 引数で渡してください。**トークンをファイルに書いてコミットしないでください。**

### テスト

```bash
python -m unittest discover -s scripts/test -t .
```

### 設計資料

変更の前に [README](README.md) からリンクされている `docs/` の資料と、関連する `specs/` を確認してください。
特に、取得するデータの項目を追加・変更する場合は、`scripts/utils.py` の `EVENT_DATA_VERSION` を1つ上げ、[docs/data_model.md](docs/data_model.md) の更新を同じ Pull Request に含めてください。

### Pull Request

1. このリポジトリを fork し、作業用のブランチを作る
2. 変更を加え、テストが通ることを確認する
3. Pull Request を作る

コミットメッセージは [Conventional Commits](https://www.conventionalcommits.org/ja/v1.0.0/) の形式(`feat:`、`fix:`、`docs:`、`chore:` など)で書いてください。
Pull Request は管理者のレビューと承認を経てマージされます。

### セキュリティ上の問題

脆弱性やトークンの漏洩を見つけた場合は、Issue ではなく [SECURITY.md](SECURITY.md) の手順で非公開に報告してください。

---

参加にあたっては [行動規範](CODE_OF_CONDUCT.md) を守ってください。
