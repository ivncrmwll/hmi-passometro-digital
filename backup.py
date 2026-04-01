import os
import shutil
from datetime import datetime

# Cria a pasta de backups se não existir
os.makedirs('backups', exist_ok=True)
data_atual = datetime.now().strftime('%Y-%m-%d_%H-%M')

# Localiza o banco de dados
caminho_db = 'instance/passometro.db' if os.path.exists('instance/passometro.db') else 'passometro.db'
destino = f'backups/passometro_{data_atual}.db'

try:
    shutil.copy2(caminho_db, destino)
    print(f"Backup concluído com sucesso: {destino}")
except Exception as e:
    print(f"Erro ao fazer backup: {e}")