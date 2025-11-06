#pragma once
#include "service_19.h"
#include "model_19.h"
#include <memory>

class Controller19 {
public:
    Controller19();
    void initialize();
    void run();
private:
    std::unique_ptr<Service19> service_;
    std::shared_ptr<Model19> model_;
};
