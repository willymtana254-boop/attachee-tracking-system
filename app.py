from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
import os

app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'change-this-in-production')
jwt = JWTManager(app)

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# Serve the logo at /klf-logo.webp
@app.route('/klf-logo.webp')
def logo():
    return send_from_directory('static', 'klf-logo.webp')

if __name__ == '__main__':
    app.run(debug=False)
