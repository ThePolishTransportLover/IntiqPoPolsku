#!/usr/bin/env python3
import sys
import asyncio
import threading
from PyQt5 import QtWidgets, QtCore
from slixmpp import ClientXMPP


class ChatWindow(QtWidgets.QWidget):
    def __init__(self, jid, xmpp, contact_jid):
        super().__init__()
        self.jid = jid
        self.xmpp = xmpp
        self.contact_jid = contact_jid
        self.setWindowTitle(f"Czat z {contact_jid}")

        self.resize(400, 300)
        self.layout = QtWidgets.QVBoxLayout()

        self.chat_area = QtWidgets.QTextEdit()
        self.chat_area.setReadOnly(True)

        self.msg_input = QtWidgets.QLineEdit()
        self.msg_input.returnPressed.connect(self.send_message)

        self.layout.addWidget(self.chat_area)
        self.layout.addWidget(self.msg_input)
        self.setLayout(self.layout)

    def display_message(self, sender, message):
        self.chat_area.append(f"<b>{sender}:</b> {message}")

    def send_message(self):
        message = self.msg_input.text().strip()
        if message:
            self.xmpp.send_message(mto=self.contact_jid, mbody=message, mtype='chat')
            self.display_message("Ty", message)
            self.msg_input.clear()


class XMPPClient(ClientXMPP):
    def __init__(self, jid, password, main_window):
        super().__init__(jid, password)
        self.main_window = main_window
        self.chat_windows = {}

        self.add_event_handler("session_start", self.start)
        self.add_event_handler("message", self.message)
        self.add_event_handler("roster_update", self.roster_updated)
        self.add_event_handler("failed_auth", self.failed_auth)

    async def start(self, event):
        self.send_presence()
        await self.get_roster()
        QtCore.QMetaObject.invokeMethod(
            self.main_window,
            "update_roster",
            QtCore.Qt.QueuedConnection,
        )

    def roster_updated(self, iq):
        QtCore.QMetaObject.invokeMethod(
            self.main_window,
            "update_roster",
            QtCore.Qt.QueuedConnection,
        )

    def message(self, msg):
        if msg['type'] in ('chat', 'normal'):
            sender = str(msg['from']).bare
            body = msg['body']
            if sender not in self.chat_windows:
                QtCore.QMetaObject.invokeMethod(
                    self.main_window,
                    "open_chat_window",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, sender)
                )
            self.chat_windows[sender].display_message(sender, body)

    def failed_auth(self, event):
        QtCore.QMetaObject.invokeMethod(
            self.main_window,
            "show_login_error",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, "Błędne dane logowania! Sprawdź JID i hasło.")
        )
        self.disconnect()


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Intiq - XMPP komunikator")
        self.resize(400, 300)

        self.xmpp = None
        self.jid = None

        self.layout = QtWidgets.QVBoxLayout()
        self.setLayout(self.layout)

        # --- Logowanie ---
        self.login_jid = QtWidgets.QLineEdit()
        self.login_jid.setPlaceholderText("JID (np. user@jabber.org)")

        self.login_password = QtWidgets.QLineEdit()
        self.login_password.setPlaceholderText("Hasło")
        self.login_password.setEchoMode(QtWidgets.QLineEdit.Password)

        self.login_server = QtWidgets.QLineEdit()
        self.login_server.setPlaceholderText("Serwer (np. jabber.org)")

        self.login_button = QtWidgets.QPushButton("Zaloguj się")
        self.login_button.clicked.connect(self.do_login)

        self.layout.addWidget(self.login_jid)
        self.layout.addWidget(self.login_password)
        self.layout.addWidget(self.login_server)
        self.layout.addWidget(self.login_button)

    def do_login(self):
        jid = self.login_jid.text().strip()
        password = self.login_password.text()
        server = self.login_server.text().strip()

        if not jid or not password or not server:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Wypełnij wszystkie pola")
            return

        self.jid = jid
        self.xmpp = XMPPClient(jid, password, self)

        def start_xmpp():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.xmpp.connect(address=(server, 5222)))
                loop.run_until_complete(self.xmpp.process(forever=False))
            except Exception as e:
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "show_connection_error",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, str(e))
                )

        threading.Thread(target=start_xmpp, daemon=True).start()

        self.build_roster_ui()

    @QtCore.pyqtSlot(str)
    def show_connection_error(self, message):
        QtWidgets.QMessageBox.critical(self, "Błąd połączenia", message)

    def build_roster_ui(self):
        # Czyścimy layout
        for i in reversed(range(self.layout.count())):
            widget = self.layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # Lista kontaktów
        self.buddy_list = QtWidgets.QListWidget()
        self.buddy_list.itemDoubleClicked.connect(self.chat_with_contact)

        # Dodawanie kontaktu
        self.new_contact_input = QtWidgets.QLineEdit()
        self.new_contact_input.setPlaceholderText("Dodaj kontakt (np. user@jabber.org)")

        self.add_contact_button = QtWidgets.QPushButton("Dodaj kontakt")
        self.add_contact_button.clicked.connect(self.add_contact)

        self.layout.addWidget(self.buddy_list)
        self.layout.addWidget(self.new_contact_input)
        self.layout.addWidget(self.add_contact_button)

        # Dodaj schowek (czat z samym sobą)
        self.buddy_list.addItem(self.jid)

    @QtCore.pyqtSlot()
    def update_roster(self):
        if not self.xmpp:
            return
        self.buddy_list.clear()
        self.buddy_list.addItem(self.jid)  # schowek - czat z sobą

        roster = self.xmpp.client_roster
        for group in roster.groups():
            for jid in roster.groups()[group]:
                if jid != self.jid:
                    self.buddy_list.addItem(jid)

    def add_contact(self):
        new_jid = self.new_contact_input.text().strip()
        if new_jid:
            try:
                self.xmpp.send_presence_subscription(pto=new_jid)
                QtWidgets.QMessageBox.information(self, "Dodano", f"Wysłano zaproszenie do {new_jid}")
                self.new_contact_input.clear()
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie udało się dodać kontaktu: {e}")

    def chat_with_contact(self, item):
        jid = item.text()
        self.open_chat_window(jid)

    @QtCore.pyqtSlot(str)
    def open_chat_window(self, jid):
        if jid not in self.xmpp.chat_windows:
            window = ChatWindow(self.jid, self.xmpp, jid)
            self.xmpp.chat_windows[jid] = window
            window.show()
        else:
            self.xmpp.chat_windows[jid].raise_()
            self.xmpp.chat_windows[jid].activateWindow()

    @QtCore.pyqtSlot(str)
    def show_login_error(self, message):
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle("Błąd logowania")
        msg_box.setText(message)
        msg_box.setIcon(QtWidgets.QMessageBox.Critical)

        btn_ok = msg_box.addButton(QtWidgets.QMessageBox.Ok)
        btn_clipboard = msg_box.addButton("Przejdź do Schowka", QtWidgets.QMessageBox.ActionRole)

        msg_box.exec_()

        if msg_box.clickedButton() == btn_clipboard:
            if self.jid and self.xmpp:
                self.open_chat_window(self.jid)


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

