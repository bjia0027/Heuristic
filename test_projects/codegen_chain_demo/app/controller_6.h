#pragma once
#include "service_6.h"
#include "model_6.h"
#include <memory>

class Controller6 {
public:
    Controller6();
    void initialize();
    void run();
private:
    std::unique_ptr<Service6> service_;
    std::shared_ptr<Model6> model_;
};
