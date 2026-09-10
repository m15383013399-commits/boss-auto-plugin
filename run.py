#!/usr/bin/env python3
from pathlib import Path
from app.server import make_server

if __name__=='__main__':
    server=make_server(Path(__file__).resolve().parent/'data')
    print('定向投递工作台：http://127.0.0.1:8765 · 草稿模式',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();server.store.close()
