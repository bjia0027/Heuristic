#pragma once
#include "service_36.h"
#include "model_36.h"
#include <memory>

class Controller36 {
public:
    Controller36();
    void initialize();
    void run();
private:
    std::unique_ptr<Service36> service_;
    std::shared_ptr<Model36> model_;
};
