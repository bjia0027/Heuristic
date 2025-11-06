#pragma once
#include "service_20.h"
#include "model_20.h"
#include <memory>

class Controller20 {
public:
    Controller20();
    void initialize();
    void run();
private:
    std::unique_ptr<Service20> service_;
    std::shared_ptr<Model20> model_;
};
