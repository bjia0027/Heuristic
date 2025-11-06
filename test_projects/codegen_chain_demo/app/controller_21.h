#pragma once
#include "service_21.h"
#include "model_21.h"
#include <memory>

class Controller21 {
public:
    Controller21();
    void initialize();
    void run();
private:
    std::unique_ptr<Service21> service_;
    std::shared_ptr<Model21> model_;
};
