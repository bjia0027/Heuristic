#pragma once
#include "service_34.h"
#include "model_34.h"
#include <memory>

class Controller34 {
public:
    Controller34();
    void initialize();
    void run();
private:
    std::unique_ptr<Service34> service_;
    std::shared_ptr<Model34> model_;
};
