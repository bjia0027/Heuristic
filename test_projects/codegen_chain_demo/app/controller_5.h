#pragma once
#include "service_5.h"
#include "model_5.h"
#include <memory>

class Controller5 {
public:
    Controller5();
    void initialize();
    void run();
private:
    std::unique_ptr<Service5> service_;
    std::shared_ptr<Model5> model_;
};
