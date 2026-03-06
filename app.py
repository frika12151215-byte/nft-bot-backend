from flask import Flask, send_file, request, jsonify
import sqlite3

app = Flask(__name__)

@app.route('/wheel')
def wheel():
    return send_file('templates/wheel.html')  # или просто 'wheel.html', если файл в той же папке

@app.route('/withdraw_form')
def withdraw_form():
    return send_file('templates/withdraw_form.html')

@app.route('/api/get_spins')
def get_spins():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'no user_id'}), 400
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT spins FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    spins = row[0] if row else 0
    conn.close()
    return jsonify({'spins': spins})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
