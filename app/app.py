from flask import Flask, render_template
from db import get_db_connection, release_db_connection
from routes import register_blueprints

app = Flask(__name__)
app.secret_key = 'data_base_project_abhi_jakub_2025'
register_blueprints(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/view')
def view():
    return render_template('view.html')

@app.route('/manage')
def manage():
    return render_template('manage.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)