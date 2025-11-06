#pragma once
#include "service_29.h"
#include "model_29.h"
#include <memory>

class Controller29 {
public:
    Controller29();
    void initialize();
    void run();
private:
    std::unique_ptr<Service29> service_;
    std::shared_ptr<Model29> model_;
};
