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
