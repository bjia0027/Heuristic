#pragma once
#include "service_2.h"
#include "model_2.h"
#include <memory>

class Controller2 {
public:
    Controller2();
    void initialize();
    void run();
private:
    std::unique_ptr<Service2> service_;
    std::shared_ptr<Model2> model_;
};
