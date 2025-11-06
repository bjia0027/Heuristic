#pragma once
#include "service_15.h"
#include "model_15.h"
#include <memory>

class Controller15 {
public:
    Controller15();
    void initialize();
    void run();
private:
    std::unique_ptr<Service15> service_;
    std::shared_ptr<Model15> model_;
};
