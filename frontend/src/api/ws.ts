// WebSocket к Gateway: ws(s)://<host>/ws/v1?token=<access>. Автопереподключение.
// Протокол: клиент → {type, request_id, payload}; сервер → {type, request_id, payload},
// ответ на команду — "<type>.ok" или "error". См. services/gateway/src/gateway/ws/handlers.py
export type WsMessage = { type: string; request_id: string | null; payload: unknown };

export type WsConnection = {
  send: (type: string, payload?: unknown) => string | null;
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
      setTimeout(open, 1000 * retry); // берём свежий токен при переподключении
    };
  };

  open();
  return {
    send(type, payload = {}) {
      if (!socket || socket.readyState !== WebSocket.OPEN) return null;
      const request_id = crypto.randomUUID();
      socket.send(JSON.stringify({ type, request_id, payload }));
      return request_id;
    },
    close() {
      closed = true;
      socket?.close();
    },
  };
}
