#pragma once
#include "service_1.h"
#include "model_1.h"
#include <memory>

class Controller1 {
public:
    Controller1();
    void initialize();
    void run();
private:
    std::unique_ptr<Service1> service_;
    std::shared_ptr<Model1> model_;
};
