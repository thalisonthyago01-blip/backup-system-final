import threading


class ClientTray:
    """Ícone residente do Backup Client na bandeja do Windows."""

    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.icon = None

    @staticmethod
    def _imagem():
        from PIL import Image, ImageDraw

        imagem = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        desenho = ImageDraw.Draw(imagem)

        # Caixa de backup estilizada.
        desenho.rounded_rectangle((8, 8, 56, 56), radius=10, fill=(42, 42, 48, 255))
        desenho.rounded_rectangle((15, 17, 49, 50), radius=5, fill=(235, 235, 240, 255))
        desenho.rectangle((20, 23, 44, 29), fill=(42, 42, 48, 255))
        desenho.rectangle((20, 33, 38, 38), fill=(42, 42, 48, 255))
        desenho.rectangle((20, 42, 42, 46), fill=(42, 42, 48, 255))
        return imagem

    def _sair(self, _icon=None, _item=None):
        self.stop_event.set()
        if self.icon is not None:
            self.icon.stop()

    def _mostrar_status(self, _icon=None, _item=None):
        if self.icon is not None:
            self.icon.notify(
                "O Backup Client está ativo e aguardando tarefas.",
                "Backup Client",
            )

    def executar(self):
        try:
            import pystray
        except ImportError:
            # Sem a dependência, o agent continua funcionando normalmente.
            return

        menu = pystray.Menu(
            pystray.MenuItem("Status: ativo", self._mostrar_status),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Encerrar client", self._sair),
        )

        self.icon = pystray.Icon(
            "backup-system-client",
            self._imagem(),
            "Backup Client",
            menu,
        )
        self.icon.run()
