import csv
import os
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="flask_limiter")
from io import StringIO
from flask import Flask, render_template, request, redirect, url_for, session, Response, abort
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
import pytz
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback_local_apenas')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///passometro.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)
fuso_manaus = pytz.timezone('America/Manaus')
csrf = CSRFProtect(app)
ips_liberados = set()

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

@limiter.request_filter
def verificar_ip_liberado():
    return request.remote_addr in ips_liberados

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cpf = db.Column(db.String(11), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    cargo = db.Column(db.String(50), nullable=False)
    setor = db.Column(db.String(50)) 
    senha_hash = db.Column(db.String(256), nullable=False)

class Plantao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prontuario = db.Column(db.String(20))
    setor = db.Column(db.String(50), nullable=False) 
    leito = db.Column(db.String(20), nullable=False)
    nome_paciente = db.Column(db.String(100), nullable=False)
    idade = db.Column(db.String(10))
    tipo_parto = db.Column(db.String(50))
    dados_rn = db.Column(db.String(100))
    diagnostico = db.Column(db.String(200))
    observacoes = db.Column(db.Text)
    enfermeiro_resp = db.Column(db.String(50))
    status = db.Column(db.String(20), default='Internado')
    data_admissao = db.Column(db.DateTime, default=datetime.now) 
    data_alta = db.Column(db.DateTime, nullable=True)
    motivo_evasao = db.Column(db.Text, nullable=True) # NOVA COLUNA

class RegistroLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_hora = db.Column(db.DateTime, default=datetime.now)
    usuario_nome = db.Column(db.String(100))
    setor_usuario = db.Column(db.String(50))
    acao = db.Column(db.String(200))

def registrar_log(acao):
    if session.get('logado'):
        try:
            log = RegistroLog(
                usuario_nome=session.get('usuario_nome'),
                setor_usuario=session.get('usuario_setor'),
                acao=acao
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"[ERRO] Falha ao registrar log: {e}")

with app.app_context():
    db.create_all()
        # Atualiza o banco existente sem perder dados
    if not Usuario.query.filter_by(cpf='00000000000').first():
        admin = Usuario(cpf='00000000000', nome='Ivan (TI)', cargo='Global Admin', setor='Todos', senha_hash=generate_password_hash(os.environ.get('ADMIN_SENHA', 'admin123')))
        db.session.add(admin)
        db.session.commit()

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 30 per hour")
def login():
    if request.method == 'POST':
        usuario = Usuario.query.filter_by(cpf=request.form['cpf']).first()
        if usuario and check_password_hash(usuario.senha_hash, request.form['senha']):
            session['logado'] = True
            session['usuario_id'] = usuario.id
            session['usuario_nome'] = usuario.nome
            session['usuario_cargo'] = usuario.cargo
            session['usuario_setor'] = usuario.setor
            return redirect(url_for('index'))
        return render_template('login.html', erro="CPF ou senha incorretos!")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- PAINEL ADMIN ---
@app.route('/admin')
def admin():
    if not session.get('logado') or session.get('usuario_cargo') not in ['Global Admin', 'Coord. de Ala']:
        return redirect(url_for('index'))
    
    if session.get('usuario_cargo') == 'Global Admin':
        usuarios = Usuario.query.all()
    else:
        usuarios = Usuario.query.filter_by(setor=session.get('usuario_setor')).all()
        
    return render_template('admin.html', usuarios=usuarios)

@app.route('/admin/novo_usuario', methods=['GET', 'POST'])
def novo_usuario():
    if not session.get('logado') or session.get('usuario_cargo') not in ['Global Admin', 'Coord. de Ala']:
        return redirect(url_for('index'))

    if request.method == 'POST':
        if Usuario.query.filter_by(cpf=request.form['cpf']).first():
            return render_template('novo_usuario.html', erro="CPF já cadastrado!")

        novo_usu = Usuario(
            cpf=request.form['cpf'], nome=request.form['nome'], cargo=request.form['cargo'],
            setor=request.form['setor'], senha_hash=generate_password_hash(request.form['senha'])
        )
        db.session.add(novo_usu)
        registrar_log(f"Cadastrou o usuário {novo_usu.nome} ({novo_usu.cargo})")
        db.session.commit()
        return redirect(url_for('admin'))
    return render_template('novo_usuario.html')

@app.route('/admin/resetar/<int:id>')
def resetar_senha(id):
    if not session.get('logado'): return redirect(url_for('login'))
    
    usu = db.session.get(Usuario, id) or abort(404)
    cargo_logado = session.get('usuario_cargo')
    setor_logado = session.get('usuario_setor')

    # Regra de Segurança: Quem pode resetar quem?
    pode_resetar = False
    if cargo_logado == 'Global Admin' and usu.cargo != 'Global Admin':
        pode_resetar = True
    elif cargo_logado == 'Coord. de Ala' and usu.cargo == 'Enfermeiro(a)' and usu.setor == setor_logado:
        pode_resetar = True

    if pode_resetar:
        usu.senha_hash = generate_password_hash(os.environ.get('RESET_SENHA', 'mudar123'))
        db.session.commit()
        
    return redirect(url_for('admin'))

@app.route('/admin/excluir/<int:id>')
def excluir_usuario(id):
    if not session.get('logado'): return redirect(url_for('login'))
    
    usu = db.session.get(Usuario, id) or abort(404)
    cargo_logado = session.get('usuario_cargo')
    setor_logado = session.get('usuario_setor')
    id_logado = session.get('usuario_id')

    if usu.id == id_logado: return redirect(url_for('admin'))
    pode_excluir = False

    if cargo_logado == 'Global Admin' and usu.cargo != 'Global Admin':
        pode_excluir = True
    elif cargo_logado == 'Coord. de Ala' and usu.cargo == 'Enfermeiro(a)' and usu.setor == setor_logado:
        pode_excluir = True

    if pode_excluir:
        registrar_log(f"Excluiu o usuário {usu.nome} ({usu.cargo})")
        db.session.delete(usu)
        db.session.commit()
        
    return redirect(url_for('admin'))

# --- ROTAS PRINCIPAIS ---
@app.route('/')
def index():
    setor_filtro = request.args.get('setor')
    aba_altas = request.args.get('altas')
    pagina = request.args.get('pagina', 1, type=int)
    por_pagina = 10
    limite_24h = datetime.now(fuso_manaus) - timedelta(hours=24)

    usuario_logado = session.get('logado', False)

    total_internados = Plantao.query.filter_by(status='Internado').count()
    altas_24h = Plantao.query.filter(Plantao.status == 'Alta', Plantao.data_alta >= limite_24h).count()
    total_setor = Plantao.query.filter_by(status='Internado', setor=setor_filtro).count() if setor_filtro else 0

    if aba_altas == 'true':
        paginacao = Plantao.query.filter(
            Plantao.status == 'Alta',
            Plantao.data_alta >= limite_24h
        ).paginate(page=pagina, per_page=por_pagina, error_out=False)
        return render_template('index.html',
            plantoes=paginacao.items,
            paginacao=paginacao,
            aba_altas=True,
            total_internados=total_internados,
            altas_24h=altas_24h,
            total_setor=total_setor,
            logado=usuario_logado)

    query = Plantao.query.filter_by(status='Internado')
    if setor_filtro:
        query = query.filter_by(setor=setor_filtro)

    paginacao = query.paginate(page=pagina, per_page=por_pagina, error_out=False)

    return render_template('index.html',
        plantoes=paginacao.items,
        paginacao=paginacao,
        setor_atual=setor_filtro,
        aba_altas=False,
        total_internados=total_internados,
        altas_24h=altas_24h,
        total_setor=total_setor,
        logado=usuario_logado)

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar():
    if not session.get('logado'): return redirect(url_for('login'))
    if request.method == 'POST':
        novo_plantao = Plantao(
            prontuario=request.form.get('prontuario', ''), setor=request.form['setor'], leito=request.form['leito'],
            nome_paciente=request.form['nome_paciente'], idade=request.form.get('idade', ''), tipo_parto=request.form.get('tipo_parto', ''),
            dados_rn=request.form.get('dados_rn', ''), diagnostico=request.form.get('diagnostico', ''), observacoes=request.form.get('observacoes', ''),
            enfermeiro_resp=session.get('usuario_nome')
        )
        db.session.add(novo_plantao)
        registrar_log(f"Adicionou o paciente {novo_plantao.nome_paciente} no setor {novo_plantao.setor} (Leito {novo_plantao.leito})")
        db.session.commit()
        return redirect(url_for('index', setor=novo_plantao.setor))
    return render_template('novo_paciente.html')

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    if not session.get('logado'): return redirect(url_for('login'))
    paciente = db.session.get(Plantao, id) or abort(404)
    if request.method == 'POST':
        paciente.prontuario = request.form.get('prontuario', '')
        paciente.setor = request.form['setor']
        paciente.leito = request.form['leito']
        paciente.nome_paciente = request.form['nome_paciente']
        paciente.idade = request.form.get('idade', '')
        paciente.tipo_parto = request.form.get('tipo_parto', '')
        paciente.dados_rn = request.form.get('dados_rn', '')
        paciente.diagnostico = request.form.get('diagnostico', '')
        paciente.observacoes = request.form.get('observacoes', '')
        registrar_log(f"Editou/Movimentou o paciente {paciente.nome_paciente} para o setor {paciente.setor} (Leito {paciente.leito})")
        db.session.commit()
        return redirect(url_for('index', setor=paciente.setor))
    return render_template('editar.html', paciente=paciente)

# --- FUNÇÃO DE SEGURANÇA ---
def tem_permissao_na_ala(setor_paciente):
    cargo = session.get('usuario_cargo')
    setor_logado = session.get('usuario_setor')
    if cargo == 'Global Admin' or setor_logado == 'Todos': return True
    return setor_logado == setor_paciente

# --- NOVAS ROTAS DE AÇÃO ---
@app.route('/alta/<int:id>')
def alta(id):
    if not session.get('logado'): return redirect(url_for('login'))
    paciente = db.session.get(Plantao, id) or abort(404)
    
    if not tem_permissao_na_ala(paciente.setor) or paciente.setor in ['Orquídeas', 'Acolhimento/Emergência', 'Centro Cirúrgico']:
        return redirect(url_for('index')) # Bloqueado por regra de negócio

    paciente.status = 'Alta'
    paciente.data_alta = datetime.now(fuso_manaus)
    registrar_log(f"Deu alta para o paciente {paciente.nome_paciente} ({paciente.setor})")
    db.session.commit()
    return redirect(url_for('index', altas='true'))

@app.route('/transferir/<int:id>', methods=['GET', 'POST'])
def transferir(id):
    if not session.get('logado'): return redirect(url_for('login'))
    paciente = db.session.get(Plantao, id) or abort(404)
    
    if not tem_permissao_na_ala(paciente.setor): return redirect(url_for('index'))

    if request.method == 'POST':
        setor_antigo = paciente.setor
        paciente.setor = request.form['novo_setor']
        paciente.leito = request.form['novo_leito']
        registrar_log(f"Transferiu {paciente.nome_paciente} de {setor_antigo} para {paciente.setor} (Leito {paciente.leito})")
        db.session.commit()
        return redirect(url_for('index', setor=paciente.setor))
    return render_template('transferir.html', paciente=paciente)

@app.route('/evasao/<int:id>', methods=['GET', 'POST'])
def evasao(id):
    if not session.get('logado'): return redirect(url_for('login'))
    paciente = db.session.get(Plantao, id) or abort(404)
    
    if not tem_permissao_na_ala(paciente.setor): return redirect(url_for('index'))

    if request.method == 'POST':
        paciente.status = 'Evasão'
        paciente.motivo_evasao = request.form['motivo']
        paciente.data_alta = datetime.now(fuso_manaus) # Usa a data de alta como data da evasão
        registrar_log(f"Registrou EVASÃO do paciente {paciente.nome_paciente}. Motivo: {paciente.motivo_evasao}")
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('evasao.html', paciente=paciente)

@app.route('/exportar/<formato>/<periodo>')
def exportar(formato, periodo):
    if not session.get('logado'):
        return redirect(url_for('login'))

    # Define o período do filtro
    if periodo == '24h':
        limite = datetime.now(fuso_manaus) - timedelta(hours=24)
    elif periodo == '7d':
        limite = datetime.now(fuso_manaus) - timedelta(days=7)
    elif periodo == '30d':
        limite = datetime.now(fuso_manaus) - timedelta(days=30)
    else:
        limite = datetime.now(fuso_manaus) - timedelta(hours=24)

    # Busca os pacientes conforme cargo do usuário
    cargo = session.get('usuario_cargo')
    setor = session.get('usuario_setor')

    if cargo == 'Global Admin' or setor == 'Todos':
        pacientes = Plantao.query.filter(Plantao.data_admissao >= limite).all()
    else:
        pacientes = Plantao.query.filter(
            Plantao.data_admissao >= limite,
            Plantao.setor == setor
        ).all()

    # --- EXPORTAÇÃO EM CSV ---
    if formato == 'csv':
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Prontuário', 'Setor', 'Leito', 'Paciente',
                         'Idade', 'Diagnóstico', 'Status',
                         'Data Admissão', 'Data Alta'])
        for p in pacientes:
            writer.writerow([
                p.prontuario, p.setor, p.leito, p.nome_paciente,
                p.idade, p.diagnostico, p.status,
                p.data_admissao.strftime('%d/%m/%Y %H:%M') if p.data_admissao else '',
                p.data_alta.strftime('%d/%m/%Y %H:%M') if p.data_alta else ''
            ])
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=passometro_{periodo}.csv'}
        )

    # --- EXPORTAÇÃO EM PDF ---
    elif formato == 'pdf':
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 10, f'Relatório Passômetro - Período: {periodo}', new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.set_font('Helvetica', '', 9)
        pdf.cell(0, 8, f'Gerado em: {datetime.now(fuso_manaus).strftime("%d/%m/%Y %H:%M")} | Usuário: {session.get("usuario_nome")}', new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.ln(4)

        # Cabeçalho da tabela
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_fill_color(200, 200, 200)
        pdf.cell(20, 7, 'Prontuário', border=1, fill=True)
        pdf.cell(30, 7, 'Setor', border=1, fill=True)
        pdf.cell(15, 7, 'Leito', border=1, fill=True)
        pdf.cell(50, 7, 'Paciente', border=1, fill=True)
        pdf.cell(20, 7, 'Status', border=1, fill=True)
        pdf.cell(30, 7, 'Admissão', border=1, fill=True)
        pdf.ln()

        # Linhas de dados
        pdf.set_font('Helvetica', '', 8)
        for p in pacientes:
            pdf.cell(20, 6, str(p.prontuario or ''), border=1)
            pdf.cell(30, 6, str(p.setor or ''), border=1)
            pdf.cell(15, 6, str(p.leito or ''), border=1)
            pdf.cell(50, 6, str(p.nome_paciente or ''), border=1)
            pdf.cell(20, 6, str(p.status or ''), border=1)
            pdf.cell(30, 6, p.data_admissao.strftime('%d/%m/%Y %H:%M') if p.data_admissao else '', border=1)
            pdf.ln()

        response = Response(
            bytes(pdf.output()),
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename=passometro_{periodo}.pdf'}
        )
        return response

    # Formato inválido
    return redirect(url_for('index'))

@app.route('/alterar_senha', methods=['GET', 'POST'])
def alterar_senha():
    if not session.get('logado'): return redirect(url_for('login'))
    
    if request.method == 'POST':
        usuario = db.session.get(Usuario, session['usuario_id'])
        if check_password_hash(usuario.senha_hash, request.form['senha_atual']):
            usuario.senha_hash = generate_password_hash(request.form['nova_senha'])
            db.session.commit()
            return redirect(url_for('index'))
        return render_template('alterar_senha.html', erro="Senha atual incorreta!")
        
    return render_template('alterar_senha.html')

@app.route('/admin/ips_bloqueados')
def ips_bloqueados():
    if not session.get('logado') or session.get('usuario_cargo') != 'Global Admin':
        return redirect(url_for('index'))
    return render_template('ips_bloqueados.html', ips_liberados=ips_liberados)

@app.route('/admin/liberar_ip', methods=['POST'])
def liberar_ip():
    if not session.get('logado') or session.get('usuario_cargo') != 'Global Admin':
        return redirect(url_for('index'))
    ip = request.form.get('ip', '').strip()
    if ip:
        ips_liberados.add(ip)
        registrar_log(f"Liberou o IP {ip} do bloqueio de rate limiting")
        db.session.commit()
    return redirect(url_for('ips_bloqueados'))

@app.route('/admin/remover_ip', methods=['POST'])
def remover_ip():
    if not session.get('logado') or session.get('usuario_cargo') != 'Global Admin':
        return redirect(url_for('index'))
    ip = request.form.get('ip', '').strip()
    if ip in ips_liberados:
        ips_liberados.discard(ip)
        registrar_log(f"Removeu o IP {ip} da lista de liberados")
        db.session.commit()
    return redirect(url_for('ips_bloqueados'))

@app.route('/admin/logs')
def ver_logs():
    if not session.get('logado') or session.get('usuario_cargo') not in ['Global Admin', 'Coord. de Ala']:
        return redirect(url_for('index'))
    
    limite_72h = datetime.now(fuso_manaus) - timedelta(hours=72)
    
    if session.get('usuario_cargo') == 'Global Admin':
        logs_recentes = RegistroLog.query.filter(RegistroLog.data_hora >= limite_72h).order_by(RegistroLog.data_hora.desc()).all()
    else:
        logs_recentes = RegistroLog.query.filter(RegistroLog.data_hora >= limite_72h, RegistroLog.setor_usuario == session.get('usuario_setor')).order_by(RegistroLog.data_hora.desc()).all()
        
    return render_template('logs.html', logs=logs_recentes)

@app.errorhandler(429)
def erro_rate_limit(e):
    ip_usuario = request.remote_addr
    return render_template('erro_429.html', ip=ip_usuario), 429

if __name__ == '__main__':
    from waitress import serve
    print("Servidor do Passômetro rodando na Intranet (Porta 5000)...")
    serve(app, host='0.0.0.0', port=5000)