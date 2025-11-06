#pragma once
#include "service_30.h"
#include "model_30.h"
#include <memory>

class Controller30 {
public:
    Controller30();
    void initialize();
    void run();
private:
    std::unique_ptr<Service30> service_;
    std::shared_ptr<Model30> model_;
};
