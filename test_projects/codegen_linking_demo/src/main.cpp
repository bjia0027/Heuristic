#include <iostream>
#include <vector>
#include <string>
#include <chrono>

// 包含所有模块
#include "foundation_component_0.h"
#include "middleware_component_0.h"
#include "application_component_0.h"

int main(int argc, char* argv[]) {
    std::cout << "=== Codegen & Linking Order DAG Demo ===" << std::endl;
    std::cout << "This demo showcases:" << std::endl;
    std::cout << "1. Phase-based compilation (Foundation -> Middleware -> Application)" << std::endl;
    std::cout << "2. Different optimization levels per phase" << std::endl;
    std::cout << "3. Strict linking order enforcement via DAG" << std::endl;
    std::cout << std::endl;
    
    auto start = std::chrono::high_resolution_clock::now();
    
    // Phase 1: Foundation layer
    std::cout << "[Phase 1] Initializing Foundation layer..." << std::endl;
    auto foundation_comp = foundation::createComponent0();
    foundation_comp->process();
    
    // Phase 2: Middleware layer
    std::cout << "[Phase 2] Initializing Middleware layer..." << std::endl;
    auto middleware_comp = middleware::createComponent0();
    middleware_comp->process();
    
    // Phase 3: Application layer
    std::cout << "[Phase 3] Initializing Application layer..." << std::endl;
    auto app_comp = application::createComponent0();
    app_comp->process();
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
    
    std::cout << std::endl;
    std::cout << "All components initialized successfully!" << std::endl;
    std::cout << "Total execution time: " << duration.count() << "ms" << std::endl;
    
    return 0;
}
