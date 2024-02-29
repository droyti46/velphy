import datetime
import glob
import os

from flask import Flask, render_template, url_for, request, g, redirect, session, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

MAX_FILE_SIZE = 200 # максимальный размер файла (в МБ)

app = Flask(__name__)
app.secret_key = os.urandom(24)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.db'
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE * 1024 * 1024
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = '/login'

class User(db.Model, UserMixin):
	uid = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100), nullable=False, unique=True)
	desc = db.Column(db.Text, nullable=True)
	password = db.Column(db.String(100), nullable=False)
	models = db.relationship('MLModel', backref='author', lazy='dynamic')

	def __repr__(self):
		return f'<User {self.uid}>'

	def get_id(self):
 		return (self.uid)

class MLModel(db.Model):
	model_id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100), nullable=False)
	framework = db.Column(db.String(100), nullable=False)
	desc = db.Column(db.Text, nullable=False)
	instruction = db.Column(db.Text, nullable=False)
	user_name = db.Column(db.Integer, db.ForeignKey('user.name'))
	date = db.Column(db.DateTime, default=datetime.datetime.utcnow)

	def __repr__(self):
		return f'<MLModel {self.model_id}>'

class Dataset(db.Model):
	ds_id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100), nullable=False)
	desc = db.Column(db.Text, nullable=False)
	user_name = db.Column(db.Integer, db.ForeignKey('user.name'))
	date = db.Column(db.DateTime, default=datetime.datetime.utcnow)

	def __repr__(self):
		return f'<Dataset {self.ds_id}>'

@app.route('/')
def index():
	return render_template('index.html')

@app.route('/registration', methods=['POST', 'GET'])
def registration():
	if request.method == 'POST':
		name = request.form['name']
		password = request.form['password']
		repeat_password = request.form['repeat-password']

		if not name:
			return 'Вы не указали имя пользователя'

		if not password:
			return 'Вы не указали пароль'

		if not repeat_password:
			return 'Вы не повторили пароль'

		if password != repeat_password:
			return 'Пароли должны совпадать'

		user = User.query.filter_by(name=name).first()
		if user:
			return 'Аккаунт с таким именем пользователя уже существует'

		user = User(name=name, desc='', password=password)

		try:
			db.session.add(user)
			db.session.commit()
			return redirect('/')
		except Exception as err:
			return f'При регистрации произошла какая-то ошибка\n{err}'

		remember_me = False
		if 'remember_me' in session:
			remember_me = session['remember_me']
			session.pop('remember_me', None)
		login_user(user, remember=remember_me)

		return redirect(request.args.get('next') or url_for('index'))

	return render_template('registration.html')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/login', methods=['POST', 'GET'])
def login():
	if request.method == 'POST':
		name = request.form['name']
		password = request.form['password']

		if not name:
			return 'Вы не указали имя пользователя'

		if not password:
			return 'Вы не указали пароль'

		user = User.query.filter_by(name=name).first()
		if not user:
			return 'Не сущетсвует аккаунта с таким именем пользователя. Сперва пройдите регистрацию.'

		if user.password != password:
			return 'Неверный пароль или имя пользователя.'

		remember_me = False
		if 'remember_me' in session:
			remember_me = session['remember_me']
			session.pop('remember_me', None)
		login_user(user, remember=remember_me)

		return redirect(request.args.get('next') or url_for('index'))

	return render_template('login.html')

@app.route('/models')
def models():
	mlmodels = MLModel.query.order_by(MLModel.date.desc()).all()
	return render_template('models.html', mlmodels=mlmodels, today=datetime.date.today())

@app.route('/model/<string:model_id>')
def model(model_id):
	mlmodel = MLModel.query.filter_by(model_id=model_id).first()
	if not mlmodel:
		return 'Не сущетсвует модели с таким идентификатором'
	return render_template('model_page.html', mlmodel=mlmodel)

@app.route('/load_model', methods=['POST', 'GET'])
@login_required
def load_model():
	if request.method == 'POST':
		name = request.form['name']
		framework = request.form['framework']
		desc = request.form['desc']
		instruction = request.form['instruction']
		model_file = request.files['model_file']

		if not name:
			return 'Вы не указали название модели'

		if not framework:
			return 'Вы не указали используемый фреймворк'

		if not desc:
			return 'Вы не указали описание'

		if not instruction:
			return 'Вы не указали инструкцию'

		if not model_file.filename:
			return 'Вы не выбрали файл модели'

		mlmodel = MLModel(name=name, framework=framework, desc=desc, instruction=instruction, user_name=current_user.name)

		try:
			db.session.add(mlmodel)
			db.session.commit()
		except Exception as err:
			return f'При загрузке модели произошла какая-то ошибка\n{err}'

		model_filename = secure_filename(model_file.filename)
		extension = model_filename.split('.')[-1]
		model_file.save(os.path.join('data/models', f'{mlmodel.model_id}.{extension}'))

		return redirect('/models')

	return render_template('load_model.html', action='load')

@app.route('/edit-model/<string:model_id>', methods=['POST', 'GET'])
@login_required
def edit_model(model_id):
	if request.method == 'POST':
		mlmodel = MLModel.query.filter_by(model_id=model_id).first()
		if mlmodel.user_name != current_user.name:
			return 'Вы не может редактировать чужие модели'

		name = request.form['name']
		framework = request.form['framework']
		desc = request.form['desc']
		instruction = request.form['instruction']
		model_file = request.files['model_file']

		if not name:
			return 'Вы не указали название модели'

		if not framework:
			return 'Вы не указали используемый фреймворк'

		if not desc:
			return 'Вы не указали описание'

		if not instruction:
			return 'Вы не указали инструкцию'

		if not model_file.filename:
			return 'Вы не выбрали файл модели'

		mlmodel.name = name
		mlmodel.framework = framework
		mlmodel.desc = desc
		mlmodel.instruction = instruction

		model_filename = secure_filename(model_file.filename)
		extension = model_filename.split('.')[-1]
		model_file.save(os.path.join('data/models', f'{mlmodel.model_id}.{extension}'))

		db.session.commit()

		return redirect('/models')

	return render_template('load_model.html', action='edit')

@app.route('/delete-model/<string:model_id>')
def delete_model(model_id):
	mlmodel = MLModel.query.filter_by(model_id=model_id).first()
	if mlmodel.user_name != current_user.name:
		return 'Вы не можете удалять чужие модели'
	db.session.delete(mlmodel)
	db.session.commit()
	return redirect('/models')

@app.route('/download-model/<string:model_id>')
def download_model(model_id):
	filename = glob.glob(f'data/models/{model_id}.*')[0]
	return send_from_directory('data/models', filename.split('\\')[-1])

@app.route('/datasets')
def datasets():
	datasets = Dataset.query.order_by(Dataset.date.desc()).all()
	return render_template('datasets.html', datasets=datasets, today=datetime.date.today())

@app.route('/load_dataset', methods=['POST', 'GET'])
@login_required
def load_dataset():
	if request.method == 'POST':
		name = request.form['name']
		desc = request.form['desc']
		ds_file = request.files['model_file']

		if not name:
			return 'Вы не указали название датасета'

		if not desc:
			return 'Вы не указали описание'

		if not ds_file.filename:
			return 'Вы не выбрали файл датасета'

		dataset = Dataset(name=name, desc=desc, user_name=current_user.name)

		try:
			db.session.add(dataset)
			db.session.commit()
		except Exception as err:
			return f'При загрузке датасета произошла какая-то ошибка\n{err}'

		ds_filename = secure_filename(ds_file.filename)
		extension = ds_filename.split('.')[-1]
		ds_file.save(os.path.join('data/datasets', f'{dataset.ds_id}.{extension}'))

		return redirect('/datasets')

	return render_template('load_dataset.html')

@app.route('/dataset/<string:ds_id>')
def dataset(ds_id):
	dataset = Dataset.query.filter_by(ds_id=ds_id).first()
	if not dataset:
		return 'Не сущетсвует датасета с таким идентификатором'
	return render_template('dataset_page.html', dataset=dataset)

@app.route('/delete-dataset/<string:ds_id>')
def delete_dataset(ds_id):
	dataset = Dataset.query.filter_by(ds_id=ds_id).first()
	if dataset.user_name != current_user.name:
		return 'Вы не можете удалять чужие датасеты'
	db.session.delete(dataset)
	db.session.commit()
	return redirect('/datasets')

@app.route('/download-dataset/<string:ds_id>')
def download_dataset(ds_id):
	filename = glob.glob(f'data/datasets/{ds_id}.*')[0]
	return send_from_directory('data/datasets', filename.split('\\')[-1])

@app.route('/news')
def news():
	return render_template('news.html')

@app.route('/courses')
def courses():
	return render_template('courses.html')

@app.route('/user/<string:name>')
def user(name):
	user = User.query.filter_by(name=name).first()
	if not user:
		return 'Не сущетсвует пользователя с таким именем'
	return render_template('user_page.html', user=user, today=datetime.date.today())

@app.route('/edit-profile', methods=['POST', 'GET'])
def edit_profile():
	if request.method == 'POST':
		name = request.form['name']
		desc = request.form['desc']

		if not name:
			return 'Вы не указали имя пользователя'

		user = User.query.filter_by(name=name).first()
		if user and user.uid != current_user.uid:
			return 'Аккаунт с таким именем пользователя уже существует'

		current_user.name = name
		current_user.desc = desc

		db.session.commit()

		return redirect(f'/user/{current_user.name}')

	return render_template('edit_profile.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect('/')

@app.route('/delete-account')
def delete_account():
	db.session.delete(current_user)
	db.session.commit()
	return redirect('/')

# with app.app_context():
# 	db.create_all()

if __name__ == '__main__':
 	app.run(debug=True)