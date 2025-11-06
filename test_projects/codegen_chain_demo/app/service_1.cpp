#include "service_1.h"

Service1::Service1() {}

void Service1::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service1::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
