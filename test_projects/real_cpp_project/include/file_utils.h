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
