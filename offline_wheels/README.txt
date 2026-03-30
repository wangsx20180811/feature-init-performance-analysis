离线 Python 依赖（可选，非部署必需）
====================================

单机 ECS 部署的**主线**是：解压发布包后执行 **scripts/deploy_ecs.sh**（在线 pip 安装
requirements.txt）。本目录用于**无公网 PyPI 或希望减少下载**时的增强，**可忽略**。

若需要：在 Ubuntu 24.04 x86_64（与 ECS 一致）执行 **scripts/download_offline_wheels.sh**，
或在 Windows 上装 Docker 后执行 **scripts/download_offline_wheels_docker.sh**，再
**package_release.sh** 打包含 offline_wheels 的包。详见历史说明与 README「可选增强」。
