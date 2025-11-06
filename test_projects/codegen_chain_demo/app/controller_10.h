#pragma once
#include "service_10.h"
#include "model_10.h"
#include <memory>

class Controller10 {
public:
    Controller10();
    void initialize();
    void run();
private:
    std::unique_ptr<Service10> service_;
    std::shared_ptr<Model10> model_;
};
