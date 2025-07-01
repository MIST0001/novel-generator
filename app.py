# app.py
# 必要なライブラリをインポートします
import os
import re # 正規表現ライブラリをインポート
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

# --- アプリケーションの初期設定 ---

# Flaskアプリケーションを初期化します
app = Flask(__name__)

# 許可するオリジン（あなたのNetlifyサイトのURL）を指定
	origins = [
		"https://r18novel-generator-mist.netlify.app",
		"http://127.0.0.1:5500", # ローカルテスト用も念のため追加（ポート番号は環境に合わせて）
		"http://localhost:5500"  # ローカルテスト用
	]

	CORS(app, resources={r"/generate": {"origins": origins}})
# --- Google Generative AIの設定 ---

try:
    # 環境変数からGemini APIキーを読み込みます
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("APIキーが環境変数 'GEMINI_API_KEY' に設定されていません。")
    
    # APIキーを設定します
    genai.configure(api_key=api_key)
    
    # 使用する生成モデルを初期化します
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    # 設定中にエラーが発生した場合、コンソールに出力します
    print(f"Error initializing Generative AI: {e}")
    model = None

# --- 小説生成のコアロジック ---

def generate_novel_from_theme(theme: str) -> dict:
    """
    与えられたテーマに基づいて、6段階のプロンプトチェーンを実行し、
    小説と生成過程の情報を辞書で返します。

    Args:
        theme (str): 小説のテーマ。

    Returns:
        dict: 生成された小説やタイトル案などを含む辞書。
    """
    if not model:
        raise RuntimeError("Generative AIモデルが初期化されていません。")

    try:
        # --- Prompt 1: テーマからプロットを生成 ---
        prompt1 = f"""
        # 指示
        与えられたテーマに基づいて、小説のプロットを詳細に作成してください。
        物語の起承転結が明確にわかるように記述してください。

        # テーマ
        {theme}

        # プロット
        """
        print("--- Step 1: プロットを生成中 ---")
        plot_response = model.generate_content(prompt1)
        plot = plot_response.text
        print("--- Step 1: 完了 ---")

        # --- Prompt 2: プロットからタイトルを生成 ---
        prompt2 = f"""
        # 指示
        以下のプロットに最もふさわしい、魅力的で読者の興味を引くタイトルを3つ提案してください。
        各タイトルの前には必ず「【タイトル】」と付けてください。例：【タイトル】〇〇の冒険

        # プロット
        {plot}

        # タイトル案
        """
        print("--- Step 2: タイトルを生成中 ---")
        title_response = model.generate_content(prompt2)
        all_titles = title_response.text.strip()
        
        # 採用するタイトルを決定するロジック（より堅牢に）
        # 【タイトル】から始まる最初の行を抜き出す
        match = re.search(r'【タイトル】(.*?)$', all_titles, re.MULTILINE)
        if match:
            selected_title = match.group(1).strip()
        else:
            # 見つからない場合は最初の行を仮採用
            selected_title = all_titles.split('\n')[0].replace('【タイトル】', '').strip()
        print(f"--- Step 2: 完了（採用タイトル: {selected_title}） ---")

        # --- Prompt 3: プロットとタイトルからあらすじを生成 ---
        prompt3 = f"""
        # 指示
        以下のプロットとタイトルを基に、小説のあらすじを作成してください。
        読者が「読んでみたい」と思うような、引き込まれる文章を心がけてください。
        あらすじの前には必ず「【あらすじ】」と付けてください。

        # プロット
        {plot}

        # タイトル
        {selected_title}

        # あらすじ
        """
        print("--- Step 3: あらすじを生成中 ---")
        synopsis_response = model.generate_content(prompt3)
        all_synopses = synopsis_response.text.strip()
        
        # 採用するあらすじを決定するロジック
        # 最初の【あらすじ】ブロックを抜き出す
        synopsis_match = re.search(r'【あらすじ】(.*?)(?=【あらすじ】|\Z)', all_synopses, re.DOTALL)
        if synopsis_match:
            selected_synopsis = synopsis_match.group(1).strip()
        else:
            # 見つからない場合は全体を仮採用
            selected_synopsis = all_synopses
        print("--- Step 3: 完了 ---")

        # --- Prompt 4: 全情報を使って小説の初稿を執筆 ---
        prompt4 = f"""
        # 指示
        これまでの情報をすべて使って、小説の初稿を執筆してください。
        情景描写や登場人物の心理描写を豊かに表現してください。

        # タイトル
        {selected_title}
        
        # あらすじ
        {selected_synopsis}

        # プロット
        {plot}

        # 小説初稿
        """
        print("--- Step 4: 小説の初稿を執筆中 ---")
        draft_response = model.generate_content(prompt4)
        draft = draft_response.text
        print("--- Step 4: 完了 ---")

        # --- Prompt 5: 初稿を辛口レビュー ---
        prompt5 = f"""
        # 指示
        あなたは優秀な編集者です。以下の小説初稿をプロの視点で厳しくレビューしてください。
        物語の矛盾点、キャラクター設定の甘さ、表現の陳腐さなどを具体的に指摘し、改善案を提示してください。

        # 小説初稿
        {draft}

        # 辛口レビュー
        """
        print("--- Step 5: 初稿をレビュー中 ---")
        review_response = model.generate_content(prompt5)
        review = review_response.text
        print("--- Step 5: 完了 ---")

        # --- Prompt 6: レビューを元に最終稿を執筆 ---
        prompt6 = f"""
        # 指示
        あなたはプロの作家です。以下の小説初稿と編集者からのレビューを基に、最高の小説最終稿を執筆してください。
        レビューでの指摘事項をすべて反映し、物語をさらに高いレベルに昇華させてください。

        # 小説初稿
        {draft}

        # 編集者からのレビュー
        {review}

        # 小説最終稿
        """
        print("--- Step 6: 最終稿を執筆中 ---")
        final_novel_response = model.generate_content(prompt6)
        final_novel = final_novel_response.text
        print("--- Step 6: 完了 ---")

        # フロントに返す情報を辞書にまとめる
        return {
            "final_novel": final_novel,
            "selected_title": selected_title,
            "selected_synopsis": selected_synopsis,
            "all_titles": all_titles,
            "all_synopses": all_synopses,
            "plot": plot,
            "review": review,
            "draft": draft
        }

    except Exception as e:
        print(f"小説生成中にエラーが発生しました: {e}")
        # エラー時も辞書形式で返すようにする
        return {"error": f"エラーが発生しました: {e}"}

# --- APIエンドポイントの定義 ---

@app.route('/generate', methods=['POST'])
def generate_novel_endpoint():
    """
    POSTリクエストを受け取り、小説を生成してJSONで返すAPIエンドポイント。
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    theme = data.get('theme')

    if not theme:
        return jsonify({"error": "Missing 'theme' in request body"}), 400

    print(f"受け取ったテーマ: {theme}")
    
    try:
        # 小説生成関数を呼び出します
        result_data = generate_novel_from_theme(theme)
        
        # エラーが含まれていたら500エラーを返す
        if "error" in result_data:
            return jsonify(result_data), 500

        # 結果をJSON形式で返す
        return jsonify(result_data)
        
    except Exception as e:
        # 予期せぬエラーが発生した場合
        return jsonify({"error": str(e)}), 500

# --- アプリケーションの実行 ---

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
