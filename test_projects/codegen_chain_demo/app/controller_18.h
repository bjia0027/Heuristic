#pragma once
#include "service_18.h"
#include "model_18.h"
#include <memory>

class Controller18 {
public:
    Controller18();
    void initialize();
    void run();
private:
    std::unique_ptr<Service18> service_;
    std::shared_ptr<Model18> model_;
};
