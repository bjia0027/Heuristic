#pragma once
#include "service_0.h"
#include "model_0.h"
#include <memory>

class Controller0 {
public:
    Controller0();
    void initialize();
    void run();
private:
    std::unique_ptr<Service0> service_;
    std::shared_ptr<Model0> model_;
};
