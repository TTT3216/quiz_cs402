from flask import Flask, render_template, request, redirect, url_for, session
import json
import random
import re
import time

app = Flask(__name__)
# 本番環境では、より複雑で推測されにくいシークレットキーを使用してください
# 環境変数などから取得することをおすすめします
app.secret_key = 'your_super_secret_key_here_for_security' 

# --- ヘルパー関数 ---
def prefix_to_int(prefix):
    """アルファベットの接頭辞を整数に変換するヘルパー関数"""
    val = 0
    for char in prefix:
        val = val * 26 + (ord(char) - ord('A') + 1)
    return val

def load_all_questions(filename="words.json"):
    """JSONファイルから問題を読み込む"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        # 問題IDをキーとした辞書を作成し、高速な参照を可能にする
        questions_dict = {q.get('id'): q for q in questions if q.get('id')}
        return questions, questions_dict # リストと辞書の両方を返す
    except FileNotFoundError:
        print(f"エラー: {filename} が見つかりません。")
        return [], {}
    except json.JSONDecodeError:
        print(f"エラー: {filename} のJSON形式が不正です。")
        return [], {}
    except Exception as e:
        print(f"ファイルの読み込み中にエラーが発生しました: {e}")
        return [], {}

def get_selected_question_ids(all_questions_list, range_input):
    """入力されたID範囲に基づいて問題のIDを選択する。
       範囲指定形式でない場合は、ID、質問文、解答文の部分一致検索を試みる。
    """
    selected_question_ids = []
    
    # 入力が空の場合は全範囲
    if not range_input:
        return [q.get('id') for q in all_questions_list if q.get('id')]

    # 入力文字列をカンマで分割し、それぞれを検索条件として処理
    # 大文字に変換して統一性を保つ (部分一致検索では re.IGNORECASE を使うので大文字化は不要だが、整合性のために残す)
    search_terms = [term.strip().upper() for term in range_input.split(',') if term.strip()]
    
    # 既存の全問題IDのセット
    all_q_ids_set = {q.get('id') for q in all_questions_list if q.get('id')}

    # 最終的に選択された問題のIDを格納するセット（重複排除のため）
    found_ids_set = set()

    for term_str in search_terms:
        # 1. 従来のID範囲指定形式 (A1_001-A1_005, A1_001) を優先してチェック
        match = re.match(r'^([A-Z]+)_(\d+)(?:-([A-Z]+)_(\d+))?$', term_str)
        
        if match: # 従来の範囲指定形式に合致する場合
            start_prefix, start_num_str, end_prefix, end_num_str = match.groups()
            
            if end_prefix is None and end_num_str is None: # 単一ID指定 (例: A1_001)
                target_id_formatted = f"{start_prefix}_{int(start_num_str):03d}"
                if target_id_formatted in all_q_ids_set:
                    found_ids_set.add(target_id_formatted)
            else: # 範囲指定 (例: A1_001-A1_005)
                start_num = int(start_num_str)
                end_num = int(end_num_str)
                
                start_prefix_val = prefix_to_int(start_prefix)
                end_prefix_val = prefix_to_int(end_prefix)

                if start_prefix_val > end_prefix_val:
                    raise ValueError(f"範囲指定の開始接頭辞が終了接頭辞より大きいです: '{term_str}'")
                if start_prefix_val == end_prefix_val and start_num > end_num:
                    raise ValueError(f"範囲指定の開始番号が終了番号より大きいです: '{term_str}'")

                for q_item in all_questions_list:
                    q_id = q_item.get("id")
                    if not q_id: continue

                    q_match = re.match(r'^([A-Z]+)_(\d+)$', q_id)
                    if not q_match:
                        continue

                    q_prefix, q_num_str = q_match.groups()
                    q_num = int(q_num_str)
                    q_prefix_val = prefix_to_int(q_prefix)

                    is_in_range = False
                    if start_prefix_val == end_prefix_val:
                        if q_prefix == start_prefix and start_num <= q_num <= end_num:
                            is_in_range = True
                    elif start_prefix_val < end_prefix_val:
                        if (q_prefix_val > start_prefix_val and q_prefix_val < end_prefix_val) or \
                           (q_prefix == start_prefix and q_num >= start_num) or \
                           (q_prefix == end_prefix and q_num <= end_num):
                            is_in_range = True
                    
                    if is_in_range:
                        found_ids_set.add(q_id)
        
        else: # 2. 従来の形式に合致しない場合、ID、質問、解答での部分一致検索を試みる
            # 入力された文字列を正規表現パターンとして使用
            # re.escape() で特殊文字をエスケープし、部分一致検索を安全にする
            # re.IGNORECASE を追加することで、大文字小文字を区別しない検索が可能になります
            # 大文字化は re.IGNORECASE のため不要だが、term_str自体は元々大文字化されている
            search_pattern = re.compile(re.escape(term_str), re.IGNORECASE) 
            
            for q_item in all_questions_list:
                q_id = q_item.get("id")
                question_text = q_item.get("question", "")
                answer_text = q_item.get("answer", "")

                # IDに部分一致
                if q_id and search_pattern.search(q_id):
                    found_ids_set.add(q_id)
                # 質問文に部分一致
                elif question_text and search_pattern.search(question_text):
                    found_ids_set.add(q_id)
                # 解答に部分一致
                elif answer_text and search_pattern.search(answer_text):
                    found_ids_set.add(q_id)

    # 最終的に選択されたIDが一つもなければエラー
    if not found_ids_set:
        raise ValueError(f"指定された検索条件 '{range_input}' に合致する問題が見つかりませんでした。")
        
    # セットからリストに変換し、ID順にソートして返す
    selected_question_ids = list(found_ids_set)
    selected_question_ids.sort() # ID順にソートしておくと、毎回同じ順序になりデバッグしやすい

    return selected_question_ids

# 全問題データをロード（アプリ起動時に一度だけ）
ALL_QUESTIONS_LIST, ALL_QUESTIONS_DICT = load_all_questions()

# --- ルーティング ---

@app.before_request
def initialize_quiz_session():
    """リクエストごとにセッションを初期化または設定する"""
    # セッションの初期化は初回アクセス時のみ行われるようにする
    if 'current_question_ids' not in session:
        session['current_question_ids'] = []
        session['current_question_index'] = -1
        session['answered_questions_log'] = []
        session['quiz_status'] = 'not_started' # 'not_started', 'in_progress', 'finished'
        session['quiz_message'] = ""
        session['last_question_time'] = 0 # 問題が表示されたタイムスタンプ

@app.route('/')
def index():
    """クイズ開始画面（範囲選択）"""
    # セッション情報をクリアしてリセット
    session.clear() 
    # before_requestが実行され、新しいセッションが初期化される
    # そのため、ここでは特にセッション変数を設定し直す必要はないが、明示的に設定しても問題ない
    return render_template('index.html', error=session.pop('range_error', None))

@app.route('/start_quiz', methods=['POST'])
def start_quiz():
    """クイズを開始し、最初の問題を表示する"""
    range_input = request.form.get('range_input', '').strip()
    
    session['answered_questions_log'] = [] # 新しいクイズ開始時にログをリセット
    session['quiz_message'] = ""
    session['range_error'] = "" # エラーメッセージをクリア

    try:
        selected_question_ids = get_selected_question_ids(ALL_QUESTIONS_LIST, range_input)
        if not selected_question_ids:
            session['range_error'] = "指定された範囲に問題が見つかりませんでした。"
            return redirect(url_for('index'))

        random.shuffle(selected_question_ids) # IDリストをシャッフル
        session['current_question_ids'] = selected_question_ids
        session['current_question_index'] = 0 # 最初の問題から開始
        session['quiz_status'] = 'in_progress'
        session['last_question_time'] = int(time.time()) # 問題表示開始時間

        return redirect(url_for('quiz'))
    except ValueError as ve:
        session['range_error'] = str(ve)
        return redirect(url_for('index'))
    except Exception as e:
        session['range_error'] = f"エラーが発生しました: {e}"
        return redirect(url_for('index'))

@app.route('/quiz')
def quiz():
    """クイズ問題表示画面"""
    # クイズが進行中でないか、問題リストがない場合はトップに戻す
    if session.get('quiz_status') != 'in_progress' or not session.get('current_question_ids'):
        return redirect(url_for('index'))

    current_index = session.get('current_question_index', 0)
    question_ids = session.get('current_question_ids', [])

    # すべての問題が終了した場合
    if current_index >= len(question_ids):
        session['quiz_status'] = 'finished'
        session['quiz_message'] = "すべての問題が終了しました！" # ここはログ画面での表示用
        return redirect(url_for('log'))
    
    # 現在の問題データを取得
    current_question_id = question_ids[current_index]
    question_data = ALL_QUESTIONS_DICT.get(current_question_id)

    if not question_data: # 問題データが見つからない場合のエラーハンドリング
        session['quiz_message'] = "問題データが見つかりませんでした。次の問題に進みます。"
        session['current_question_index'] += 1
        session['last_question_time'] = int(time.time()) # 次の問題のタイマー開始時間
        session['quiz_message_shown'] = True # このフラグは次のquiz()でpopされる
        return redirect(url_for('quiz')) # 問題が見つからない場合は次の問題へリダイレクト

    # ここにあったサーバーサイドの時間切れ判定によるリダイレクトを削除しました。
    # 時間切れの処理はJavaScriptのsubmitTimeoutAnswer()に任せます。

    # メッセージは一度表示したらセッションから削除
    message_to_display = session.pop('quiz_message', None)
    session.pop('quiz_message_shown', None) # フラグも削除

    return render_template('quiz.html', 
                           question=question_data, 
                           current_index=current_index + 1, 
                           total_questions=len(question_ids),
                           message=message_to_display)

@app.route('/check_answer', methods=['POST'])
def check_answer():
    """解答をチェックし、次の問題へ進むか結果を表示する"""
    if session.get('quiz_status') != 'in_progress':
        return redirect(url_for('index'))

    user_answer = request.form.get('user_answer', '').strip()
    current_index = session.get('current_question_index', 0)
    question_ids = session.get('current_question_ids', [])

    if current_index >= len(question_ids):
        session['quiz_status'] = 'finished'
        session['quiz_message'] = "すべての問題が終了しました！"
        return redirect(url_for('log'))

    current_question_id = question_ids[current_index]
    question_data = ALL_QUESTIONS_DICT.get(current_question_id)

    if not question_data: # 問題データが見つからない場合のエラーハンドリング
        session['quiz_message'] = "問題データが見つかりませんでした。次の問題に進みます。"
        session['current_question_index'] += 1
        session['last_question_time'] = int(time.time())
        session['quiz_message_shown'] = True # メッセージを表示したことを示す
        return redirect(url_for('quiz'))

    correct_answer = question_data["answer"].strip()
    
    result_message = ""
    # user_answerが空の場合、時間切れと判断してログに記録
    if user_answer == "": # 時間切れの場合のログをより正確に
        result_message = f"時間切れ。正解は '{correct_answer}' です。"
        log_result = "時間切れ (不正解)"
    elif user_answer == correct_answer:
        result_message = "正解！"
        log_result = "正解"
    else:
        result_message = f"不正解。正解は '{correct_answer}' です。"
        log_result = "不正解"

    session['answered_questions_log'].append({
        "id": question_data.get('id', 'IDなし'),
        "question": question_data['question'],
        "user_answer": user_answer if user_answer != "" else "(未入力/時間切れ)", # ログ表示を修正
        "correct_answer": correct_answer,
        "result": log_result
    })
    
    session['quiz_message'] = result_message
    session['quiz_message_shown'] = True # メッセージを表示したことを示すフラグ
    session['current_question_index'] += 1
    session['last_question_time'] = int(time.time()) # 次の問題のタイマー開始時間

    return redirect(url_for('quiz'))

@app.route('/log')
def log():
    """回答状況一覧表示画面"""
    return render_template('log.html', answered_questions_log=session.get('answered_questions_log', []))

@app.route('/confirm_quit')
def confirm_quit():
    """終了確認画面"""
    return render_template('confirm_quit.html')

@app.route('/quit_app', methods=['POST'])
def quit_app():
    """アプリを終了する（セッションをクリアしてトップページに戻る）"""
    action = request.form.get('action')

    if action == 'show_log':
        session['quiz_status'] = 'finished'
        return redirect(url_for('log'))
    elif action == 'quit':
        session.clear()
        return redirect(url_for('index'))
    else:
        session.clear()
        return redirect(url_for('index'))

# Render.comなどのWSGIサーバーで実行するためのエントリポイント
# ローカルで開発する際は 'app.run(debug=True)' を使用
if __name__ == '__main__':
    if not ALL_QUESTIONS_LIST:
        print("エラー: words.json から問題が読み込めませんでした。アプリを終了します。")
    else:
        # ローカルでの開発用。デプロイ時にはGunicornなどが 'app' オブジェクトを自動で探し実行します。
        app.run(debug=True, host='0.0.0.0', port=5000)
