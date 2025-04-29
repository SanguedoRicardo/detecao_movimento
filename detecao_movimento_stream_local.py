import sys
import cv2
import os
import threading
import numpy as np
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, 
    QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QSlider
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer, pyqtSignal
import json
import requests
import time

# Configurações
VIDEO_URL = 'http://192.168.1.211:8080/?action=stream'  # URL do feed de vídeo
EVENTOS_DIR = os.path.expanduser('~/Downloads/momento2/eventos')  # Diretório para armazenar os vídeos gravados
JSON_DIR = os.path.expanduser('~/Downloads/momento2/jsons')  # Diretório para armazenar os eventos em formato JSON

# Função para salvar eventos
def salvar_evento(tipo, arquivo):
    """
    Função para guardar o evento em um arquivo JSON.
    Recebe o tipo de evento (por exemplo, 'movimento') e o caminho do arquivo.
    """
    evento = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "evento": tipo,
        "arquivo": arquivo
    }
    os.makedirs(JSON_DIR, exist_ok=True)  # Cria o diretório, se necessário
    nome_json = os.path.join(JSON_DIR, f"evento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(nome_json, 'w') as f:
        json.dump(evento, f, indent=4)  # Salva o evento em formato JSON

class MonitoramentoApp(QWidget):
    popup_signal = pyqtSignal(str)  # Sinal para mostrar o pop-up

    def _init_(self):
        super()._init_()
        self.setWindowTitle("Sistema de Monitoramento")  # Título da janela
        self.resize(1000, 700)  # Tamanho da janela

        # Layout principal da aplicação
        self.layout_principal = QHBoxLayout(self)

        # Menu lateral
        self.menu_lateral = QVBoxLayout()
        self.btn_live_feed = QPushButton('Live Feed')  # Botão para exibir o feed ao vivo
        self.btn_historico = QPushButton('Histórico de Movimento')  # Botão para exibir o histórico de movimentos
        self.btn_sair = QPushButton('Sair')  # Botão para sair da aplicação
        self.sensibilidade_slider = QSlider()  # Slider para ajuste de sensibilidade de movimento

        self.menu_lateral.addWidget(self.btn_live_feed)
        self.menu_lateral.addWidget(self.btn_historico)
        self.menu_lateral.addWidget(QLabel("Sensibilidade:"))  # Rótulo para o slider
        self.menu_lateral.addWidget(self.sensibilidade_slider)
        self.menu_lateral.addStretch()
        self.menu_lateral.addWidget(self.btn_sair)

        self.layout_principal.addLayout(self.menu_lateral)

        # Área principal de exibição de vídeo
        self.area_principal = QVBoxLayout()
        self.video_label = QLabel("Área Principal")  # Rótulo para exibir o vídeo
        self.video_label.setStyleSheet("background-color: black;")  # Fundo preto
        self.area_principal.addWidget(self.video_label)

        self.lista_eventos = QListWidget()  # Lista de eventos gravados
        self.lista_eventos.hide()  # Esconde a lista de eventos inicialmente
        self.area_principal.addWidget(self.lista_eventos)

        self.layout_principal.addLayout(self.area_principal)

        # Variáveis de controle
        self.cap = None  # Objeto para captura de vídeo
        self.capture_thread = None  # Thread de captura de vídeo
        self.running = False  # Flag para verificar se a captura está em andamento
        self.current_frame = None  # Último frame capturado
        self.first_frame = None  # Primeiro frame usado para comparação
        self.modo = "live"  # Modo de operação (feed ao vivo ou histórico)

        # Controles de tempo
        self.last_motion_time = None  # Última vez que o movimento foi detectado
        self.last_popup_time = None  # Última vez que o pop-up foi mostrado
        self.cooldown_seconds = 10  # Tempo de espera para reexibir o pop-up
        self.motion_duration = 30  # Tempo de duração do movimento para considerar como contínuo
        self.sensibilidade = 500  # Sensibilidade inicial para detecção de movimento

        # Slider para ajustar a sensibilidade
        self.sensibilidade_slider.setOrientation(1)  # Slider horizontal
        self.sensibilidade_slider.setRange(100, 1000)  # Faixa de valores de sensibilidade
        self.sensibilidade_slider.setValue(self.sensibilidade)  # Valor inicial da sensibilidade
        self.sensibilidade_slider.valueChanged.connect(self.atualizar_sensibilidade)  # Conecta o slider a uma função

        # Conexões de botões
        self.btn_live_feed.clicked.connect(self.mostrar_live_feed)
        self.btn_historico.clicked.connect(self.mostrar_historico)
        self.btn_sair.clicked.connect(self.fechar)
        self.lista_eventos.itemClicked.connect(self.start_reproduzir_evento)

        # Timer para atualizar o feed de vídeo
        self.timer = QTimer()
        self.timer.timeout.connect(self.atualizar_frame)
        self.timer.start(30)  # Atualiza a cada 30 milissegundos

        self.popup_signal.connect(self.mostrar_popup)  # Conecta o sinal de pop-up

        # Começar com o feed ao vivo
        self.mostrar_live_feed()

    def atualizar_sensibilidade(self, valor):
        """Função para atualizar a sensibilidade de detecção de movimento."""
        self.sensibilidade = valor

    def iniciar_captura(self):
        """Inicia a captura do feed de vídeo em uma thread separada."""
        self.running = True
        self.capture_thread = threading.Thread(target=self.captura_frames, daemon=True)
        self.capture_thread.start()

    def parar_captura(self):
        """Interrompe a captura do feed de vídeo."""
        self.running = False
        self.capture_thread = None

    def captura_frames(self):
        """Captura os frames do feed de vídeo."""
        while self.running:
            try:
                stream = requests.get(VIDEO_URL, stream=True, timeout=5)  # Conecta ao feed de vídeo
                bytes_data = b''
                for chunk in stream.iter_content(chunk_size=1024):
                    if not self.running:
                        break
                    bytes_data += chunk
                    a = bytes_data.find(b'\xff\xd8')  # Início da imagem JPEG
                    b = bytes_data.find(b'\xff\xd9')  # Fim da imagem JPEG
                    if a != -1 and b != -1:
                        jpg = bytes_data[a:b+2]  # Extrai a imagem JPEG
                        bytes_data = bytes_data[b+2:]
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)  # Converte para um frame
                        if frame is not None:
                            self.current_frame = frame  # Atualiza o frame atual
            except Exception as e:
                print(f"Erro na captura de frames: {e}")
                time.sleep(2)  # Espera antes de tentar reconectar

    def atualizar_frame(self):
        """Atualiza o frame exibido na interface gráfica."""
        if self.modo == "live" and self.running and self.current_frame is not None:
            frame = self.current_frame.copy()  # Cria uma cópia do frame

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)  # Converte para escala de cinza
            gray = cv2.GaussianBlur(gray, (21, 21), 0)  # Aplica desfoque para reduzir ruído

            if self.first_frame is None:
                self.first_frame = gray  # Define o primeiro frame
            else:
                delta_frame = cv2.absdiff(self.first_frame, gray)  # Calcula a diferença entre o primeiro frame e o atual
                thresh = cv2.threshold(delta_frame, 25, 255, cv2.THRESH_BINARY)[1]  # Aplica threshold
                thresh = cv2.dilate(thresh, None, iterations=2)  # Expande as áreas de movimento
                contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                movimento_detectado = False
                for contour in contours:
                    if cv2.contourArea(contour) >= self.sensibilidade:  # Verifica se o movimento é grande o suficiente
                        movimento_detectado = True
                        (x, y, w, h) = cv2.boundingRect(contour)  # Desenha um retângulo em torno do movimento detectado
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                if movimento_detectado:
                    if self.last_motion_time is None or (datetime.now() - self.last_motion_time).total_seconds() > self.motion_duration:
                        self.last_motion_time = datetime.now()
                        if self.last_popup_time is None or (datetime.now() - self.last_popup_time).total_seconds() > self.motion_duration:
                            threading.Thread(target=self.gravar_video, args=(frame.copy(),), daemon=True).start()
                            self.last_popup_time = datetime.now()
                            self.popup_signal.emit("Movimento detectado e gravado!")

            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Converte o frame para RGB
            h, w, ch = img.shape
            bytes_per_line = ch * w
            qt_img = QImage(img.data, w, h, bytes_per_line, QImage.Format_RGB888)  # Converte para imagem do PyQt
            self.video_label.setPixmap(QPixmap.fromImage(qt_img))  # Exibe a imagem

    def gravar_video(self, frame_atual):
        """Grava um vídeo quando movimento é detectado."""
        def gravar():
            os.makedirs(EVENTOS_DIR, exist_ok=True)  # Cria o diretório de eventos
            filename = os.path.join(EVENTOS_DIR, f"movimento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
            out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*'m', 'p', '4', 'v'), 5, (frame_atual.shape[1], frame_atual.shape[0]))
            for _ in range(50):  # Grava por 10 segundos a 5 FPS
                if self.current_frame is not None:
                    out.write(self.current_frame)
                    time.sleep(0.2)
            out.release()
            salvar_evento("Movimento", filename)  # Salva o evento em JSON

        threading.Thread(target=gravar, daemon=True).start()

    def mostrar_popup(self, mensagem):
        """Exibe uma janela de pop-up com uma mensagem."""
        from PyQt5.QtWidgets import QMessageBox
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText(mensagem)
        msg.setWindowTitle("Notificação")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

    def mostrar_live_feed(self):
        """Exibe o feed ao vivo."""
        self.modo = "live"
        self.lista_eventos.hide()
        self.video_label.show()
        self.first_frame = None
        if not self.running:
            self.iniciar_captura()

    def mostrar_historico(self):
        """Exibe o histórico de vídeos gravados."""
        self.modo = "historico"
        if self.running:
            self.parar_captura()
        self.lista_eventos.clear()
        self.lista_eventos.show()
        self.video_label.hide()
        os.makedirs(EVENTOS_DIR, exist_ok=True)
        arquivos = sorted([f for f in os.listdir(EVENTOS_DIR) if f.endswith('.mp4')])
        for arquivo in arquivos:
            item = QListWidgetItem(arquivo)
            self.lista_eventos.addItem(item)

    def start_reproduzir_evento(self, item):
        """Reproduz um evento gravado."""
        caminho = os.path.join(EVENTOS_DIR, item.text())
        try:
            import subprocess
            subprocess.Popen(['open', caminho])  # Usa 'open' para o macOS
        except Exception as e:
            print(f"Erro ao tentar abrir o vídeo: {e}")

    def fechar(self):
        """Fecha a aplicação e para a captura de vídeo."""
        self.parar_captura()
        self.close()

# Executar a app
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MonitoramentoApp()
    window.show()
    sys.exit(app.exec_())