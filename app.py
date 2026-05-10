import os
import re
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from supabase import create_client

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])
supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])


def get_fridge():
    result = supabase.table('fridge').select('*').execute()
    return {row['item']: row['quantity'] for row in result.data}

def upsert_item(item, quantity):
    supabase.table('fridge').upsert({'item': item, 'quantity': quantity}).execute()

def delete_item(item):
    supabase.table('fridge').delete().eq('item', item).execute()


@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    reply = process_command(text)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))


def process_command(text):
    # 確認
    if text in ['確認', '一覧', '冷蔵庫', 'リスト']:
        fridge = get_fridge()
        if not fridge:
            return '冷蔵庫は空です。'
        lines = ['📦 冷蔵庫の中身：']
        for item, qty in sorted(fridge.items()):
            lines.append(f'・{item}：{qty}')
        return '\n'.join(lines)

    # ヘルプ
    if text in ['ヘルプ', 'help', '使い方']:
        return (
            '📋 使い方：\n'
            '「牛乳 追加」→ 1つ追加\n'
            '「牛乳 3本 追加」→ 数量指定で追加\n'
            '「牛乳 使った」→ 1つ消費\n'
            '「牛乳 2本 使った」→ 数量指定で消費\n'
            '「牛乳 削除」→ 完全に削除\n'
            '「確認」→ 在庫一覧を表示'
        )

    # 追加
    add_match = re.match(
        r'^(.+?)\s*(\d+)?\s*(?:個|本|袋|枚|缶|パック|kg|g|L|ml)?\s*追加$', text
    )
    if add_match:
        item = add_match.group(1).strip()
        qty = int(add_match.group(2)) if add_match.group(2) else 1
        fridge = get_fridge()
        new_qty = fridge.get(item, 0) + qty
        upsert_item(item, new_qty)
        return f'✅ {item} を {qty} 追加しました。（現在：{new_qty}）'

    # 消費
    use_match = re.match(
        r'^(.+?)\s*(\d+)?\s*(?:個|本|袋|枚|缶|パック|kg|g|L|ml)?\s*(?:使った|消費|食べた|飲んだ|なくなった|減った)$',
        text
    )
    if use_match:
        item = use_match.group(1).strip()
        qty = int(use_match.group(2)) if use_match.group(2) else 1
        fridge = get_fridge()
        if item not in fridge:
            return f'❌ {item} は登録されていません。'
        new_qty = fridge[item] - qty
        if new_qty <= 0:
            delete_item(item)
            return f'🗑️ {item} を消費しました。（在庫なし）'
        upsert_item(item, new_qty)
        return f'✅ {item} を {qty} 消費しました。（残り：{new_qty}）'

    # 削除
    del_match = re.match(r'^(.+?)\s*削除$', text)
    if del_match:
        item = del_match.group(1).strip()
        fridge = get_fridge()
        if item in fridge:
            delete_item(item)
            return f'🗑️ {item} を削除しました。'
        return f'❌ {item} は登録されていません。'

    return '❓ 認識できませんでした。「ヘルプ」と送ると使い方が見られます。'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
