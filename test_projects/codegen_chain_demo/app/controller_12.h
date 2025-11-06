#pragma once
#include "service_12.h"
#include "model_12.h"
#include <memory>

class Controller12 {
public:
    Controller12();
    void initialize();
    void run();
private:
    std::unique_ptr<Service12> service_;
    std::shared_ptr<Model12> model_;
};
