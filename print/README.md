# PDFの生成と確認

Markdownを原本として、公開用標準雛形3点、AIツール利用ガイドライン1点、説明版2点をA4縦のPDFに変換します。PDFは派生物であり、PDFだけを手修正しません。

## GitHub Actionsで生成する

[PDF生成ワークフロー](../.github/workflows/pdfs.yml)が標準の生成方法です。初回コミットを公開した後は、対象ファイルを更新してpushするか、GitHubの「Actions」→「Public contract PDFs」→「Run workflow」から手動実行します。pull requestでも同じ検証を行います。

実行が成功したら、その実行ページの `public-contract-pdfs` からPDF6点と `manifest.json` をダウンロードします。成果物は30日で期限切れになるため、署名に使う版は取得後に非公開の保管先へ保存してください。締結用の記入欄・署名欄は、ダウンロードしたPDFにGoogle Workspaceで付与します。署名済み文書や締結記録は、このリポジトリやActionsの成果物に戻しません。

ワークフローは読取り権限だけで、固定した公開原稿と同梱のフォントを使って生成・本文照合を行います。原稿やPDFの自動コミット、Release公開は行いません。

## 手元での確認用生成

Python 3.12を使用します。リポジトリのルートで次を実行してください。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r print/requirements.txt
.venv/bin/python scripts/build_pdfs.py
```

WindowsではPythonのパスを `.venv\Scripts\python.exe` に読み替えます。生成時の外部フォント取得はありません。

生成先は `output/pdf/` です。PDFと `manifest.json` はGit管理の対象外です。manifestには原稿とPDFのSHA-256、版、ページ数、本文照合件数を記録します。

| 原稿 | PDF |
| --- | --- |
| [業務委託基本契約書](../partner-agreement/2026-10-05.md) | `partner-agreement-2026-10-05.pdf` |
| [NDA](../nda/2026-10-05.md) | `nda-2026-10-05.pdf` |
| [情報セキュリティ遵守事項](../security-policy/2026-10-05.md) | `security-policy-2026-10-05.pdf` |
| [AIツール利用ガイドライン](../ai-guidelines/2026-10-06.md) | `ai-guidelines-2026-10-06.pdf` |
| [業務委託基本契約書・説明版](../partner-agreement/guide-2026-10-05.md) | `partner-agreement-guide-2026-10-05.pdf` |
| [NDA・説明版](../nda/guide-2026-10-05.md) | `nda-guide-2026-10-05.pdf` |

対象は [documents.json](documents.json) に固定版ファイルとして明示しています。古い版、README、CHANGELOG、フォルダ内の任意のMarkdownはPDF化しません。次の改訂時は固定版と別名ファイルを更新したうえで、この一覧の版・原稿・出力名を更新します。過去版を生成したい場合は、その版を管理していたコミットの生成設定を使用します。

## レイアウト

- A4縦、左右20 mmの余白。本文は9.4 pt、行送り16.1 ptです。説明版も文字サイズを維持し、行送りを14.4 ptとして、短い節だけが最終ページに残ることを抑えます。
- 本文の濃い紺、見出しの太さ、控えめな青緑、細い罫線で階層を示します。
- 表題の下では文書番号・版・作成日・改定履歴へのリンクを小さな情報帯にまとめ、本文の導入と視覚的に区別します。
- 各ページ左上には提供された `k.inc.brand.full.2025.svg` をベクター形式のまま配置します。原本は [印刷用アセット](assets/k.inc.brand.full.2025.svg) に同梱しています。
- 見出しを直後の本文と同じページに置き、締結欄全体を一つのブロックとして扱います。締結欄の表は、記入しやすい行高と署名用の余白を持つフォームとして描画します。
- パートナー契約の説明版は、末尾の短い節だけが独立しないよう、生成一覧の`keep_final_sections`で最後の2節をまとめています。改訂で分量が変わった場合は、目視確認のうえこの設定を調整できます。
- 全ページに文書種別、版、公開リポジトリのURL、総ページ数付きのページ番号を表示します。
- 日本語フォントをPDFに埋め込み、閲覧端末に日本語フォントがなくても表示できるようにします。
- 本文・番号付きリスト・入れ子リスト・強調・リンク・表・引用を処理します。未対応の構文は黙って削除せず、生成を失敗させます。文書間の相対リンクは公開リポジトリのURLへ変換します。

## 自動確認と目視確認

生成時に、最新版と固定版の完全一致、説明版とその固定版の完全一致、公開Markdownの相対リンク、PDFの全テキストブロック、空白ページ、日本語フォントの埋め込みを確認します。文書の意味の妥当性や法的な適合性を自動認定するものではありません。

構造だけ確認する場合は次を実行します。

```sh
.venv/bin/python scripts/check_sources.py
```

改訂時はPDFを開き、全ページの改ページ、番号、表、締結欄に欠けや重なりがないか確認してください。Popplerを利用できる環境では、次のように画像化できます。

```sh
mkdir -p tmp/pdfs/review
pdftoppm -r 120 -png output/pdf/nda-2026-10-05.pdf tmp/pdfs/review/nda
```

契約への適用版はPDFの生成日時ではなく、当事者間で合意した版により決まります。

## フォント

本文と見出しには、LINE Seed Sansの日本語書体である**LINE Seed JP**を使用します。日本語と英数字を同じファミリーで組める書体です。[Google Fontsの公式配布元](https://github.com/google/fonts/tree/main/ofl/lineseedjp)からRegularとBoldを取得して同梱し、使用文字をPDFに埋め込みます。フォントの再配布条件は同梱の[SIL Open Font License](fonts/OFL.txt)に従います。フォントはLINEヤフー株式会社が公開しています。

同梱フォントのSHA-256：Regular `04a6c0077ddb8ba5af3638bd76b4600708dde7b38df047b40fbe6f3af358d3c3`、Bold `67aec2dc10b3ad210d6f7d53b33bbfea42ea28e32fa3834624eee699a638d5ff`。

Actionsの版は公式の [checkout](https://github.com/actions/checkout/releases/tag/v7.0.1)、[setup-python](https://github.com/actions/setup-python/releases/tag/v7.0.0)、[upload-artifact](https://github.com/actions/upload-artifact/releases/tag/v7.0.1) を確認しています。
