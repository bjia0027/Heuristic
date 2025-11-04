#!/bin/bash
# 创建一个真实的可编译C++测试项目

PROJECT_DIR="/home/jia/桌面/distcc-3.4/test_projects/real_cpp_project"
rm -rf "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/src"
mkdir -p "$PROJECT_DIR/include"
mkdir -p "$PROJECT_DIR/build"

echo "创建真实C++测试项目..."

# 创建头文件
cat > "$PROJECT_DIR/include/math_utils.h" << 'EOF'
#ifndef MATH_UTILS_H
#define MATH_UTILS_H

namespace MathUtils {
    double add(double a, double b);
    double subtract(double a, double b);
    double multiply(double a, double b);
    double divide(double a, double b);
}

#endif
EOF

cat > "$PROJECT_DIR/include/string_utils.h" << 'EOF'
#ifndef STRING_UTILS_H
#define STRING_UTILS_H

#include <string>
#include <vector>

namespace StringUtils {
    std::string toUpper(const std::string& str);
    std::string toLower(const std::string& str);
    std::vector<std::string> split(const std::string& str, char delim);
    std::string join(const std::vector<std::string>& parts, const std::string& delim);
}

#endif
EOF

cat > "$PROJECT_DIR/include/file_utils.h" << 'EOF'
#ifndef FILE_UTILS_H
#define FILE_UTILS_H

#include <string>
#include <vector>

namespace FileUtils {
    std::string readFile(const std::string& filename);
    bool writeFile(const std::string& filename, const std::string& content);
    std::vector<std::string> listFiles(const std::string& directory);
    bool fileExists(const std::string& filename);
}

#endif
EOF

# 创建源文件（20个文件）
for i in {1..20}; do
    cat > "$PROJECT_DIR/src/module_${i}.cpp" << EOF
#include <iostream>
#include <vector>
#include <string>
#include <cmath>
#include "../include/math_utils.h"
#include "../include/string_utils.h"

namespace Module${i} {
    double calculate() {
        double result = 0.0;
        for (int j = 0; j < 1000; j++) {
            result += MathUtils::add(j * 0.5, std::sin(j));
        }
        return result;
    }
    
    std::string process(const std::string& input) {
        auto parts = StringUtils::split(input, ',');
        return StringUtils::join(parts, ";");
    }
    
    void test() {
        std::cout << "Module ${i} - Result: " << calculate() << std::endl;
        std::cout << "Module ${i} - Processed: " << process("a,b,c,d") << std::endl;
    }
}
EOF
done

# math_utils.cpp
cat > "$PROJECT_DIR/src/math_utils.cpp" << 'EOF'
#include "../include/math_utils.h"

namespace MathUtils {
    double add(double a, double b) { return a + b; }
    double subtract(double a, double b) { return a - b; }
    double multiply(double a, double b) { return a * b; }
    double divide(double a, double b) { return b != 0 ? a / b : 0; }
}
EOF

# string_utils.cpp  
cat > "$PROJECT_DIR/src/string_utils.cpp" << 'EOF'
#include "../include/string_utils.h"
#include <algorithm>
#include <sstream>

namespace StringUtils {
    std::string toUpper(const std::string& str) {
        std::string result = str;
        std::transform(result.begin(), result.end(), result.begin(), ::toupper);
        return result;
    }
    
    std::string toLower(const std::string& str) {
        std::string result = str;
        std::transform(result.begin(), result.end(), result.begin(), ::tolower);
        return result;
    }
    
    std::vector<std::string> split(const std::string& str, char delim) {
        std::vector<std::string> result;
        std::stringstream ss(str);
        std::string item;
        while (std::getline(ss, item, delim)) {
            result.push_back(item);
        }
        return result;
    }
    
    std::string join(const std::vector<std::string>& parts, const std::string& delim) {
        std::string result;
        for (size_t i = 0; i < parts.size(); i++) {
            if (i > 0) result += delim;
            result += parts[i];
        }
        return result;
    }
}
EOF

# file_utils.cpp
cat > "$PROJECT_DIR/src/file_utils.cpp" << 'EOF'
#include "../include/file_utils.h"
#include <fstream>
#include <sstream>
#include <sys/stat.h>
#include <dirent.h>

namespace FileUtils {
    std::string readFile(const std::string& filename) {
        std::ifstream file(filename);
        std::stringstream buffer;
        buffer << file.rdbuf();
        return buffer.str();
    }
    
    bool writeFile(const std::string& filename, const std::string& content) {
        std::ofstream file(filename);
        if (!file.is_open()) return false;
        file << content;
        return true;
    }
    
    std::vector<std::string> listFiles(const std::string& directory) {
        std::vector<std::string> files;
        DIR* dir = opendir(directory.c_str());
        if (dir) {
            struct dirent* entry;
            while ((entry = readdir(dir)) != nullptr) {
                files.push_back(entry->d_name);
            }
            closedir(dir);
        }
        return files;
    }
    
    bool fileExists(const std::string& filename) {
        struct stat buffer;
        return (stat(filename.c_str(), &buffer) == 0);
    }
}
EOF

# main.cpp
cat > "$PROJECT_DIR/src/main.cpp" << 'EOF'
#include <iostream>
#include "../include/math_utils.h"
#include "../include/string_utils.h"
#include "../include/file_utils.h"

// 声明外部模块
namespace Module1 { void test(); }
namespace Module2 { void test(); }
namespace Module3 { void test(); }
namespace Module4 { void test(); }
namespace Module5 { void test(); }

int main() {
    std::cout << "=== Real C++ Project Test ===" << std::endl;
    
    // 测试数学工具
    std::cout << "Math: 10 + 5 = " << MathUtils::add(10, 5) << std::endl;
    
    // 测试字符串工具
    std::cout << "String: " << StringUtils::toUpper("hello") << std::endl;
    
    // 测试模块
    Module1::test();
    Module2::test();
    
    std::cout << "=== Test Complete ===" << std::endl;
    return 0;
}
EOF

# 生成compile_commands.json
cat > "$PROJECT_DIR/compile_commands.json" << 'EOF'
[
EOF

# 为每个源文件生成编译命令
first=true
for file in "$PROJECT_DIR"/src/*.cpp; do
    filename=$(basename "$file" .cpp)
    if [ "$first" = false ]; then
        echo "," >> "$PROJECT_DIR/compile_commands.json"
    fi
    first=false
    
    cat >> "$PROJECT_DIR/compile_commands.json" << ENTRY
{
  "directory": "$PROJECT_DIR",
  "command": "g++ -c -I$PROJECT_DIR/include -std=c++17 -O2 -Wall $file -o $PROJECT_DIR/build/${filename}.o",
  "file": "$file"
}
ENTRY
done

cat >> "$PROJECT_DIR/compile_commands.json" << 'EOF'
]
EOF

echo "✅ 项目创建完成: $PROJECT_DIR"
echo "   源文件: $(ls $PROJECT_DIR/src/*.cpp | wc -l) 个"
echo "   编译命令: $PROJECT_DIR/compile_commands.json"


