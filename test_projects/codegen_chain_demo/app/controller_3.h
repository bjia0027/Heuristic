#pragma once
#include "service_3.h"
#include "model_3.h"
#include <memory>

class Controller3 {
public:
    Controller3();
    void initialize();
    void run();
private:
    std::unique_ptr<Service3> service_;
    std::shared_ptr<Model3> model_;
};
