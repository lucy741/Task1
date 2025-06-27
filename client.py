import socket       # TCP网络通信
import sys          # 命令行参数解析
import os           # 文件路径检查
import random       # 生成随机块大小
from typing import List, Tuple  # 类型注解
import argparse
class ReverseClient:
    def __init__(self, server_ip, server_port, lmin, lmax, input_file, output_file):
        self.server_ip = server_ip        # 服务器IP地址
        self.server_port = server_port    # 服务器端口号
        self.lmin = lmin                  # 块大小最小值
        self.lmax = lmax                  # 块大小最大值
        self.input_file = input_file      # 原始文件路径
        self.output_file = output_file    # 反转后文件路径
        self.socket = None                # 存储套接字对象
        self.block_sizes = []             # 存储各块大小的列表

    def connect(self):
        """连接到服务器"""
        # 创建TCP套接字（IPv4 + TCP协议）
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 连接到服务器
        self.socket.connect((self.server_ip, self.server_port))
        print(f"已连接到服务器: {self.server_ip}:{self.server_port}")

    def disconnect(self):
        """断开与服务器的连接"""
        if self.socket:
            self.socket.close()  # 关闭套接字，释放资源
            print("已断开与服务器的连接")

    def generate_block_sizes(self, file_size: int) -> List[int]:
        """生成随机块大小列表"""
        remaining_size = file_size  # 剩余未分块的字节数
        block_sizes = []  # 存储各块大小的列表

        while remaining_size > 0:
            if remaining_size <= self.lmin:
                # 最后一块：剩余大小可能小于lmin，直接使用
                block_sizes.append(remaining_size)
                break
            else:
                # 随机生成块大小：在[lmin, min(lmax, 剩余大小)]范围内
                block_size = random.randint(self.lmin, min(self.lmax, remaining_size))
                block_sizes.append(block_size)
                remaining_size -= block_size  # 扣除已分块的大小

        return block_sizes

    def send_initialization(self, num_blocks: int):
        """发送初始化报文"""
        # 构造初始化报文：Type=0x0001（2字节大端序） + 块数N（4字节大端序）
        packet_type = 0x0001
        packet = packet_type.to_bytes(2, 'big') + num_blocks.to_bytes(4, 'big')
        self.socket.sendall(packet)  # 发送完整报文

        # 接收服务器的Agree响应（6字节：Type=0x0002 + 4字节块数）
        response = self.socket.recv(6)
        if len(response) != 6 or int.from_bytes(response[0:2], 'big') != 0x0002:
            raise Exception("未收到有效的Agree响应")

        # 解析服务器返回的块数，验证是否与发送的一致
        received_n = int.from_bytes(response[2:6], 'big')
        if received_n != num_blocks:
            raise Exception(f"服务器返回的块数不匹配: 期望 {num_blocks}，实际 {received_n}")

        print(f"初始化成功，块数: {num_blocks}")

    def process_file(self):
        """处理文件并发送到服务器"""
        try:
            # 以二进制模式读取原始文件
            with open(self.input_file, 'rb') as f:
                file_content = f.read()     # 读取整个文件为字节串

            # 验证文件内容是否全为ASCII可打印字符（ASCII码32-126）
            if not all(32 <= byte <= 126 for byte in file_content):
                raise Exception("文件包含非ASCII可打印字符")

            file_size = len(file_content)
            if file_size == 0:
                raise Exception("文件为空")

            # 生成块大小列表
            self.block_sizes = self.generate_block_sizes(file_size)     # 生成分块方案
            num_blocks = len(self.block_sizes)
            print(f"文件将被分成 {num_blocks} 块")

            # 发送初始化报文
            self.send_initialization(num_blocks)

            # 初始化反转后的内容（字节数组，可高效拼接）
            reversed_content = bytearray()
            offset = 0  # 当前处理的文件偏移量（当前处理位置）

            for i, block_size in enumerate(self.block_sizes):
                # 提取当前块数据（从offset开始，长度为block_size）
                block_data = file_content[offset:offset + block_size]
                offset += block_size  # 更新偏移量

                # 构造反转请求报文：Type=0x0003（2字节） + 长度（4字节） + 数据
                packet_type = 0x0003
                packet = packet_type.to_bytes(2, 'big') + len(block_data).to_bytes(4, 'big') + block_data
                self.socket.sendall(packet)
                print(f"第 {i + 1} 块已发送")

                # 接收服务器返回的反转结果
                # 先接收头部（4字节：Type=0x04 + 长度）
                header = self.socket.recv(6)
                if len(header) != 6 or int.from_bytes(header[0:2], 'big') != 0x0004:
                    raise Exception(f"第 {i + 1} 块: 未收到有效的ReverseAnswer响应")

                reversed_length = int.from_bytes(header[2:6], 'big')  # 从第3字节开始解析长度,获取反转后的长度

                # 循环接收反转数据，确保收满全部字节
                reversed_data = b''
                while len(reversed_data) < reversed_length:
                    chunk = self.socket.recv(reversed_length - len(reversed_data))  #接收一个数据块
                    if not chunk:
                        raise Exception(f"第 {i + 1} 块: 接收数据不完整")
                    reversed_data += chunk
                    print(f"已接收第 {i + 1} 块数据 {len(chunk)} 字节")

                # 将反转数据添加到结果中
                reversed_content.extend(reversed_data)

                # 解码为ASCII字符串并打印（替换不可解码的字符，避免报错）
                reversed_text = reversed_data.decode('ascii', errors='replace')
                print(f"{i + 1}:{reversed_text}")
                print(f"第 {i + 1} 块反转结果: {reversed_text}")

            # 将反转后的字节流写入输出文件
            with open(self.output_file, 'wb') as f:
                f.write(reversed_content)

            print(f"文件处理完成，反转后的内容已保存到: {self.output_file}")

        except Exception as e:
            print(f"处理文件时出错: {e}")
            raise  # 重新抛出异常，让上层处理


if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='TCP文件反转客户端')

    # 添加必需参数
    parser.add_argument('--server_ip', required=True, help='服务器IP地址')
    parser.add_argument('--server_port', type=int, required=True, help='服务器端口号')
    parser.add_argument('--lmin', type=int, required=True, help='最小块大小')
    parser.add_argument('--lmax', type=int, required=True, help='最大块大小')
    parser.add_argument('--input_file', required=True, help='输入文件名')
    parser.add_argument('--output_file', required=True, help='输出文件名')
    print("python client.py --server_ip 127.0.0.1 --server_port 12345 --lmin 50 --lmax 200 --input_file test_input.txt --output_file test_output.txt")
    # 解析命令行参数
    args = parser.parse_args()

    # 参数验证
    if args.lmin <= 0 or args.lmax <= 0 or args.lmin > args.lmax:
        print("错误: lmin和lmax必须为正整数，且lmin <= lmax")
        sys.exit(1)

    if not os.path.exists(args.input_file):
        print(f"错误: 输入文件 '{args.input_file}' 不存在")
        sys.exit(1)

    client = ReverseClient(args.server_ip, args.server_port, args.lmin, args.lmax,
                           args.input_file, args.output_file)

    try:
        client.connect()
        client.process_file()
    except Exception as e:
        print(f"客户端运行出错: {e}")
        sys.exit(1)
    finally:
        client.disconnect()