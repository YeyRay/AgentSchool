#!/bin/bash
# Script for testing observer functionality

# ========== Set environment variables ==========
echo "========================================"
echo "🔧 Setting environment variables..."
echo "========================================"

# 1. Set API Key (replace with your actual API Key)
export SCHOOLAGENT_API_KEY="11"

# 2. Set Embedding model paths
# BGE_MODEL: Used by student modules for exercises and prompts
# BGE_MODEL_L: Used by teacher vector database (typically uses larger model)

# Option 1: Use bge-small-zh-v1.5 for students (recommended, faster)
export BGE_MODEL="/mnt/shared-storage-user/zhangbo1/models/bge-small-zh-v1.5"

# Option 2: Use bge-large-zh for teacher (more accurate)
export BGE_MODEL_L="/mnt/shared-storage-user/zhangbo1/models/bge-large-zh"

# Alternative configurations:
# Use same model for both:
# export BGE_MODEL="/mnt/shared-storage-user/zhangbo1/models/bge-small-zh-v1.5"
# export BGE_MODEL_L="/mnt/shared-storage-user/zhangbo1/models/bge-small-zh-v1.5"

# Use Hugging Face model names (requires network download):
# export BGE_MODEL="BAAI/bge-small-zh-v1.5"
# export BGE_MODEL_L="BAAI/bge-large-zh"

echo "✅ SCHOOLAGENT_API_KEY: ${SCHOOLAGENT_API_KEY:0:20}"
echo "✅ BGE_MODEL (student): $BGE_MODEL"
echo "✅ BGE_MODEL_L (teacher): $BGE_MODEL_L"

# ========== Check if model files exist ==========
echo ""
echo "========================================"
echo "📁 Checking model files..."
echo "========================================"

# Check student model (BGE_MODEL)
if [ -d "$BGE_MODEL" ]; then
    echo "✅ Student model path exists: $BGE_MODEL"
    ls -lh "$BGE_MODEL" | head -3
else
    echo "⚠️  Student model path does not exist: $BGE_MODEL"
    echo "   Will attempt to download from Hugging Face..."
fi

echo ""

# Check teacher model (BGE_MODEL_L)
if [ -d "$BGE_MODEL_L" ]; then
    echo "✅ Teacher model path exists: $BGE_MODEL_L"
    ls -lh "$BGE_MODEL_L" | head -3
else
    echo "⚠️  Teacher model path does not exist: $BGE_MODEL_L"
    echo "   Will attempt to download from Hugging Face..."
fi

# ========== Check API Key ==========
echo ""
echo "========================================"
echo "🔑 Checking API Key..."
echo "========================================"

if [ "$SCHOOLAGENT_API_KEY" = "your_api_key_here" ]; then
    echo "❌ Error: Please set your SCHOOLAGENT_API_KEY first"
    echo "   Edit this script and replace 'your_api_key_here' with your actual API Key"
    exit 1
else
    echo "✅ API Key is set"
fi

# ========== Start simulation ==========
echo ""
echo "========================================"
echo "🚀 Starting simulation..."
echo "========================================"
echo "Tips: "
echo "  1. After simulation starts, open another terminal"
echo "  2. Edit observer_cmd.json file to send commands"
echo "  3. Press Ctrl+C to stop at any time"
echo ""
echo "Starting to run..."
echo ""

python run.py

echo ""
echo "========================================"
echo "✅ Simulation ended"
echo "========================================"

