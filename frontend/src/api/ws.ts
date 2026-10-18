// WebSocket к Gateway: ws(s)://<host>/ws/v1?token=<access>. Переподключается сам.
// Сервер шлёт {type, payload}; клиент может послать {type: "ping"}.
// См. services/gateway/src/gateway/ws.py
export type WsMessage = { type: string; payload: unknown };

export type WsConnection = {
  send: (type: string, payload?: unknown) => void;
  close: () => void;
};

export function connectWs(getToken: () => string | null, onMessage: (msg: WsMessage) => void): WsConnection {
  let socket: WebSocket | null = null;
  let closed = false;
  let retry = 0;

  const open = () => {
    const token = getToken();
    if (!token || closed) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${proto}://${location.host}/ws/v1?token=${encodeURIComponent(token)}`);
    socket.onopen = () => {
      retry = 0;
    };
    socket.onmessage = (event) => onMessage(JSON.parse(event.data as string) as WsMessage);
    socket.onclose = () => {
      if (closed) return;
      retry = Math.min(retry + 1, 5);
      setTimeout(open, 1000 * retry); // при переподключении берём свежий токен
    };
  };

  open();
  return {
    send(type, payload = {}) {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type, payload }));
    },
    close() {
      closed = true;
      socket?.close();
    },
  };
}
