#pragma once
#include "service_28.h"
#include "model_28.h"
#include <memory>

class Controller28 {
public:
    Controller28();
    void initialize();
    void run();
private:
    std::unique_ptr<Service28> service_;
    std::shared_ptr<Model28> model_;
};
