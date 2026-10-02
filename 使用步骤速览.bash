# 1. 创建目录 & 拷贝文件
mkdir -p realestate_risk/{projects,cache,output}
cd realestate_risk
# 把上面 16 个文件逐个创建（或把 FILES 字典填好跑 bootstrap.py）

# 2. 装依赖
pip install -r requirements.txt

# 3. 放入待分析项目到 projects/ 目录

# 4. 编辑 run.sh（或 run.bat）顶部大模型三行配置
#    或直接 export LLM_BASE_URL / LLM_API_KEY / LLM_MODEL

# 5. 运行
chmod +x run.sh && ./run.sh