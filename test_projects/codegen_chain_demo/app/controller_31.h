#pragma once
#include "service_31.h"
#include "model_31.h"
#include <memory>

class Controller31 {
public:
    Controller31();
    void initialize();
    void run();
private:
    std::unique_ptr<Service31> service_;
    std::shared_ptr<Model31> model_;
};
