/**
 * 採用AIメディア自動化基盤: 管理用スプレッドシートの初期構築スクリプト。
 *
 * 使い方(docs/setup/02_google_sheets.md に画面単位の手順あり):
 * 1. 空のGoogleスプレッドシートを新規作成する
 * 2. メニュー「拡張機能」→「Apps Script」を開く
 * 3. デフォルトのコードを全て消し、このファイルの内容を貼り付けて保存する
 * 4. 関数選択で setupSpreadsheet を選び、実行(▶)する
 * 5. 初回は権限の承認画面が出るので、自分のGoogleアカウントで許可する
 *
 * 何度実行しても安全(すでにあるシートは作り直さず、ヘッダーだけ確認する)。
 */

function setupSpreadsheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  const sheetDefs = [
    {
      name: '設定',
      headers: ['項目', '値', '説明', '最終更新日'],
      seed: [
        ['MONTHLY_BUDGET_JPY', 3000, '月間API予算上限(円)', new Date()],
        ['WEEKLY_POST_TARGET', 3, '週間の投稿目標本数', new Date()],
        ['IG_ACCOUNT_MODE', 'test', 'test または production', new Date()],
        ['YT_ACCOUNT_MODE', 'test', 'test または production', new Date()],
      ],
    },
    {
      name: '企画候補',
      headers: [
        'ID', '作成日', 'タイトル案', '切り口', 'フォーマット', '出典URL',
        '専門性', '需要', '収益性', '独自性', 'リスク', '合計スコア',
        '重複チェック', '要人間承認', '承認理由', 'ステータス',
      ],
    },
    {
      name: '投稿カレンダー',
      headers: [
        'ID', '企画候補ID', '投稿予定日時', 'プラットフォーム', 'アカウント種別',
        'ステータス', '担当エージェント', '最終更新日時', '備考',
      ],
      validations: {
        'ステータス': ['下書き', 'AI校閲済み', '承認待ち', '承認', '修正', '却下', '投稿予約', '投稿済み', 'エラー'],
        'プラットフォーム': ['Instagram', 'YouTube Shorts'],
        'アカウント種別': ['test', 'production'],
      },
    },
    {
      name: '投稿原稿',
      headers: [
        'ID', '投稿カレンダーID', 'Instagramキャプション', 'カルーセルスライド(JSON)',
        'YouTube台本', 'CTA', 'PR表記有無', '校閲結果', '修正指示', 'バージョン', '更新日時',
      ],
    },
    {
      name: '記事',
      headers: [
        'ID', 'タイトル', '本文', '公開URL', '公開ステータス',
        '関連アフィリエイト案件ID', '出典一覧', '公開日', '更新日',
      ],
      validations: { '公開ステータス': ['下書き', '公開済み'] },
    },
    {
      name: 'アフィリエイト案件',
      headers: [
        'ID', 'サービス名', 'ジャンル', '報酬条件', 'PR表記文言',
        '承認状況', '承認日', '契約リンク', '備考',
      ],
      validations: { '承認状況': ['承認待ち', '承認', '却下'] },
    },
    {
      name: '投稿実績',
      headers: [
        'ID', '投稿カレンダーID', 'プラットフォーム', '投稿URL', '投稿日時',
        '再生数', '表示数', '保存数', 'クリック数', '問い合わせ数', '取得日',
      ],
    },
    {
      name: '分析',
      headers: ['週', '上位テーマ', '上位構成', '上位冒頭表現', '下位テーマ傾向', '来週への提案', '作成日'],
    },
    {
      name: 'エラーログ',
      headers: ['発生日時', 'エージェント/処理', 'エラー内容', '対象ID', 'リトライ回数', '対応状況', '対応者', '解決日時'],
      validations: { '対応状況': ['未対応', '対応中', '解決済み'] },
    },
    {
      name: '週間レポート',
      headers: ['週', '投稿本数', '記事本数', 'API利用額(今週)', 'API利用額(今月)', '目標達成率', '確認が必要な項目', '来週の申し送り', '作成日'],
    },
  ];

  sheetDefs.forEach(function (def) {
    const sheet = getOrCreateSheet_(ss, def.name);
    ensureHeaders_(sheet, def.headers);
    if (def.seed && sheet.getLastRow() <= 1) {
      sheet.getRange(2, 1, def.seed.length, def.headers.length).setValues(def.seed);
    }
    if (def.validations) {
      applyValidations_(sheet, def.headers, def.validations);
    }
  });

  // Apps Scriptが自動生成するデフォルトの空シート("シート1"/"Sheet1")は、
  // 中身が空で、かつ他のシートが作成済みなら削除する。
  ['シート1', 'Sheet1'].forEach(function (defaultName) {
    const s = ss.getSheetByName(defaultName);
    if (s && s.getLastRow() === 0 && ss.getSheets().length > 1) {
      ss.deleteSheet(s);
    }
  });

  SpreadsheetApp.getUi().alert('セットアップ完了: 10シートを作成しました。');
}

function getOrCreateSheet_(ss, name) {
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
  }
  return sheet;
}

function ensureHeaders_(sheet, headers) {
  const range = sheet.getRange(1, 1, 1, headers.length);
  const existing = range.getValues()[0];
  const isEmpty = existing.every(function (v) { return v === ''; });
  if (isEmpty) {
    range.setValues([headers]);
    sheet.setFrozenRows(1);
    range.setFontWeight('bold').setBackground('#e1efe9');
  }
}

function applyValidations_(sheet, headers, validations) {
  Object.keys(validations).forEach(function (colName) {
    const colIndex = headers.indexOf(colName) + 1;
    if (colIndex === 0) return;
    const rule = SpreadsheetApp.newDataValidation()
      .requireValueInList(validations[colName], true)
      .setAllowInvalid(false)
      .build();
    // 見出し行を除く、当面の運用に十分な行数(500行)まで適用する。
    sheet.getRange(2, colIndex, 500, 1).setDataValidation(rule);
  });
}
