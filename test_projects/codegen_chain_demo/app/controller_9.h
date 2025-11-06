#pragma once
#include "service_9.h"
#include "model_9.h"
#include <memory>

class Controller9 {
public:
    Controller9();
    void initialize();
    void run();
private:
    std::unique_ptr<Service9> service_;
    std::shared_ptr<Model9> model_;
};
