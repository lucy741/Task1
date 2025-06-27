import socket       #用于TCP网络通信
import threading    #用于多线程处理客户端连接
import sys          #用于命令行参数解析
from typing import Dict, List, Tuple  # 类型注解，增强代码可读性
import argparse
class ReverseServer:
    def __init__(self,host,port):   #初始化服务参数
        self.host = host  # 服务器监听的IP地址（如'0.0.0.0'或'localhost'）
        self.port = port  # 服务器监听的端口号
        self.server_socket = None  # 存储服务器套接字对象
        self.clients = {}  # 存储客户端线程的字典（键：客户端ID，值：线程对象）
        self.client_id = 0  # 客户端ID计数器
        self.lock = threading.Lock()  # 线程锁，确保多线程安全
    def start(self):    #启动服务器
        """启动服务器"""
        #套接字就像信箱是具体接收和发送物品的地方。每个套接字由 IP 地址和端口号（相当于信箱编号）唯一确定。
        # 创建TCP套接字（AF_INET=IPv4，SOCK_STREAM=TCP协议）
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # 设置套接字选项：允许同一端口在程序重启后立即使用（避免端口被占用时的错误）
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # 绑定IP地址和端口
        self.server_socket.bind((self.host, self.port))

        # 开始监听，最大等待连接数为5
        self.server_socket.listen(5)
        print(f"服务器已启动，监听地址: {self.host}:{self.port}")

        try:
            while True:
                # 阻塞式等待客户端连接，直到有客户端连接时才会返回，返回值为客户端套接字和地址（如('192.168.1.100', 50000)）。
                client_socket, client_address = self.server_socket.accept()

                # 由于多个线程可能同时尝试增加client_id，使用锁可以确保这个操作的原子性，避免 ID 冲突。
                with self.lock:
                    self.client_id += 1
                    client_id = self.client_id  # 获取当前客户端ID

                print(f"新客户端连接: {client_address}, ID: {client_id}")

                # 创建新线程处理该客户端，daemon=True表示守护线程（随主线程退出而结束）
                client_thread = threading.Thread(
                    target=self.handle_client,  # 线程执行的函数，该函数负责与客户端通信。
                    args=(client_socket, client_address, client_id),  # 传递给函数的参数
                    daemon=True  #将线程设置为守护线程，意味着当主线程退出时，这些线程会自动终止。
                )
                client_thread.start()  # 启动线程
                self.clients[client_id] = client_thread  # 记录线程到字典中

        except KeyboardInterrupt:  # 捕获Ctrl+C中断
            print("\n服务器关闭中...")
        finally:
            self.server_socket.close()  # 关闭服务器套接字
            print("服务器已关闭")

    def handle_client(self, client_socket: socket.socket, client_address: Tuple[str, int], client_id: int):
        """处理客户端请求"""
        try:
            while True:
                # 接收报文头（至少6字节：2字节类型 + 4字节长度）
                header = client_socket.recv(6)
                if not header:  # 客户端断开连接时，recv返回空字节
                    break

                # 解析报文类型和长度
                packet_type = int.from_bytes(header[:2], 'big')
                data_length = int.from_bytes(header[2:6], 'big')

                # 根据报文类型处理
                if packet_type == 0x01:  # 初始化报文
                    # 初始化报文只有6字节，没有额外数据
                    self.handle_initialization(client_socket, header)
                elif packet_type == 0x03:  # 反转请求报文
                    # 接收完整数据
                    remaining = data_length
                    data = bytearray()
                    while remaining > 0:
                        chunk = client_socket.recv(min(remaining, 4096))
                        if not chunk:
                            raise ConnectionResetError("连接意外关闭")
                        data.extend(chunk)
                        remaining -= len(chunk)
                    self.handle_reverse_request(client_socket, header, data)
                else:
                    print(f"客户端 {client_id}: 未知报文类型: {packet_type}")
                    break

        except ConnectionResetError:
            print(f"客户端 {client_id} 连接重置")
        except Exception as e:
            print(f"处理客户端 {client_id} 时出错: {e}")
        finally:
            client_socket.close()
            with self.lock:
                if client_id in self.clients:
                    del self.clients[client_id]
            print(f"客户端连接已关闭: {client_address}, ID: {client_id}")

    def handle_initialization(self, client_socket, header):
        """处理初始化报文"""
        # 解析块数N：header[2:6]是4字节的大端整数（从第3字节到第6字节）
        n = int.from_bytes(header[2:6], 'big')
        print(f"收到初始化请求: 块数 = {n}")

        # 发送Agree响应：2字节类型0x0002 + 4字节块数N
        response_type = 0x0002      #代表 “同意” 响应类型
        #将整数 0x0002 转换为 2 字节的大端序字节串 b'\x00\x02'，将块数 n（如 5）转换为 4 字节的大端序字节串。
        #最终 response 是一个 6 字节的字节串
        response = response_type.to_bytes(2, 'big') + n.to_bytes(4, 'big')
        client_socket.sendall(response) #发送响应，确保整个响应字节串完整发送，不会中途中断。

    def handle_reverse_request(self, client_socket, header, data):
        """处理反转请求报文"""
        # 解析数据长度：header[2:6]是4字节的大端整数（从第3字节到第6字节）
        data_length = int.from_bytes(header[2:6], 'big')

        # 验证接收到的数据长度是否与报头中的长度一致
        if len(data) != data_length:
            raise ValueError(f"数据长度不匹配：报头中声明 {data_length} 字节，但实际接收 {len(data)} 字节")

        # 反转数据（字节流反转，如b'abc' → b'cba'）
        reversed_data = data[::-1]
        #发送反转结果
        # 构造反转响应报文：2字节类型0x0004 + 4字节长度 + 反转后的数据
        response_type = 0x0004  #代表这是反转响应
        response = response_type.to_bytes(2, 'big') + len(reversed_data).to_bytes(4, 'big') + reversed_data
        client_socket.sendall(response)
        print(f"已向客户端发送反转数据，长度: {len(reversed_data)} 字节")


if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='TCP文件反转服务器')

    # 添加必需参数
    parser.add_argument('--host', required=True, help='服务器监听IP地址')
    parser.add_argument('--port', type=int, required=True, help='服务器监听端口号')

    print("python server.py --host 127.0.0.1 --port 12345")
    # 解析命令行参数
    args = parser.parse_args()

    # 参数验证
    if args.port <= 0 or args.port > 65535:
        print("错误: 端口号必须在1-65535之间")
        sys.exit(1)

    server = ReverseServer(args.host, args.port)
    server.start()