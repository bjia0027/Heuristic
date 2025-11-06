#pragma once
#include "service_11.h"
#include "model_11.h"
#include <memory>

class Controller11 {
public:
    Controller11();
    void initialize();
    void run();
private:
    std::unique_ptr<Service11> service_;
    std::shared_ptr<Model11> model_;
};
